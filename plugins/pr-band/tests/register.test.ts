import { expect, mock, test } from 'claude-code/testing'
import { parse } from '../hooks/register.js'

// What Claude Code passes to a ui.render hook for the band
const BAND = {
  plugin: 'pr-band',
  component: 'AbovePrompt',
  requestId: 'above-prompt',
  surface: 'terminal',
  viewport: { columns: 120, rows: 40 },
  props: {
    hasSurvey: false,
    isWorking: false,
    maxRows: 4,
    bodyColumns: 100,
    scroll: { offset: 0, bodyRows: 4 },
    view: {},
  },
} as const

function pr(number: number, title: string, opts: { draft?: boolean; review?: string | null; rollup?: string | null }) {
  return {
    number,
    title,
    url: `https://github.com/x/y/pull/${number}`,
    isDraft: opts.draft ?? false,
    reviewDecision: opts.review ?? null,
    commits: { nodes: [{ commit: { statusCheckRollup: opts.rollup ? { state: opts.rollup } : null } }] },
  }
}

function ghOut(nodes: unknown[]) {
  return { exitCode: 0, stdout: JSON.stringify({ data: { search: { nodes } } }), stderr: '' }
}

// Stub everything the mod passes on or calls, then start the session and let the first fetch run
async function start($, on, run: ($, e) => unknown) {
  const clock = mock.clock(on)
  on('process.run', run)
  on('session.start', () => ({ cwd: '/work' }))
  on('ui.render', () => ({ type: 'Text', props: {}, children: ['drawn by Claude Code'] }))
  await $.session.start({ surface: 'terminal', isInteractive: true, cwd: '/work' })
  await clock.settle()
  return clock
}

test('draws PRs with check, approval, and ticket labels', async ($, on) => {
  await start($, on, () => ({
    value: ghOut([
      pr(2365, '[DE-3240] feat: thing', { review: 'APPROVED', rollup: 'SUCCESS' }),
      pr(2348, '[DE-3132] feat: other', { review: 'CHANGES_REQUESTED', rollup: 'FAILURE' }),
      pr(123, 'no ticket here', { draft: true, review: null, rollup: null }),
      {},
    ]),
  }))
  const ui = await $.ui.mount(BAND)
  expect(await ui.find({ type: 'Text', text: '✓✓ DE-3240' })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: '✗ DE-3132 (review)' })).toBeDefined()
  const draft = await ui.find({ type: 'Text', text: '● #123' })
  expect(draft).toBeDefined()
  expect(draft.props.dimColor).toBe(true)
  // Other mods' band content is kept
  expect(await ui.find({ type: 'Text', text: 'drawn by Claude Code' })).toBeDefined()
})

test('drafts sort after ready PRs so the cap keeps ready ones', async () => {
  const segs = parse(ghOut([
    pr(1, '[DE-1] draft', { draft: true, rollup: 'SUCCESS' }),
    pr(2, '[DE-2] ready', { rollup: 'SUCCESS' }),
    pr(3, '[DE-3] ready too', { rollup: 'PENDING' }),
  ]).stdout)
  expect(segs.map((s) => s.isDraft)).toEqual([false, false, true])
  expect(segs[0].text).toContain('DE-2')
})

test('a non-zero gh exit shows gh unavailable', async ($, on) => {
  await start($, on, () => ({ value: { exitCode: 1, stdout: '', stderr: 'boom' } }))
  const ui = await $.ui.mount(BAND)
  expect(await ui.find({ type: 'Text', text: 'PRs: gh unavailable' })).toBeDefined()
})

test('a rejected process.run shows gh unavailable and does not throw', async ($, on) => {
  await start($, on, () => ({ deny: 'gh not found' }))
  const ui = await $.ui.mount(BAND)
  expect(await ui.find({ type: 'Text', text: 'PRs: gh unavailable' })).toBeDefined()
})

test('bad JSON shows gh unavailable', async ($, on) => {
  await start($, on, () => ({ value: { exitCode: 0, stdout: 'not json', stderr: '' } }))
  const ui = await $.ui.mount(BAND)
  expect(await ui.find({ type: 'Text', text: 'PRs: gh unavailable' })).toBeDefined()
})

test('zero PRs draws nothing of its own', async ($, on) => {
  await start($, on, () => ({ value: ghOut([]) }))
  const ui = await $.ui.mount(BAND)
  expect(await ui.find({ type: 'Text', text: /PRs/ })).toBeUndefined()
  expect(await ui.find({ type: 'Text', text: 'drawn by Claude Code' })).toBeDefined()
})

test('cuts segments that do not fit the band width', async ($, on) => {
  await start($, on, () => ({
    value: ghOut([
      pr(1, '[DE-1111] a', { rollup: 'SUCCESS' }),
      pr(2, '[DE-2222] b', { rollup: 'SUCCESS' }),
      pr(3, '[DE-3333] c', { rollup: 'SUCCESS' }),
    ]),
  }))
  // "PRs" + "  ✓ DE-1111" + "  ✓ DE-2222" is 25 columns
  const ui = await $.ui.mount({ ...BAND, props: { ...BAND.props, bodyColumns: 25 } })
  expect(await ui.find({ type: 'Text', text: '✓ DE-2222' })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: '✓ DE-3333' })).toBeUndefined()
})

test('the refresh timer fetches again after the interval', async ($, on) => {
  let calls = 0
  const clock = await start($, on, () => {
    calls += 1
    return { value: ghOut([]) }
  })
  expect(calls).toBe(1)
  await clock.advance(120_000)
  expect(calls).toBe(2)
})
