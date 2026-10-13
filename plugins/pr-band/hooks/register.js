// pr-band: one row above the prompt with your open PRs, CI state, and review state.
// Data lives in module variables, not $.state, so it survives /clear.

const MAX_PRS = 6
const SEP = '  '
const PREFIX = 'PRs'

const QUERY =
  'query($q:String!){search(query:$q,type:ISSUE,first:10){nodes{... on PullRequest{' +
  'number title url isDraft reviewDecision ' +
  'commits(last:1){nodes{commit{statusCheckRollup{state}}}}}}}}'

let prs = []
let failed = false
let inFlight = false

// Turn one GraphQL PullRequest node into the bits the band draws
export function toSegment(node) {
  const key = /\[([A-Z]+-\d+)\]/.exec(node.title || '')
  const label = key ? key[1] : '#' + node.number
  const rollup = node.commits?.nodes?.[0]?.commit?.statusCheckRollup?.state
  let check = '●'
  let color = 'yellow'
  if (rollup === 'SUCCESS') {
    check = '✓'
    color = 'green'
  } else if (rollup === 'FAILURE' || rollup === 'ERROR') {
    check = '✗'
    color = 'red'
  }
  let text = check
  if (node.reviewDecision === 'APPROVED') text += '✓'
  text += ' ' + label
  if (node.reviewDecision === 'CHANGES_REQUESTED') text += ' (review)'
  return { text, color, isDraft: node.isDraft === true }
}

// Parse gh's stdout into segments, or throw if it isn't the shape we expect
export function parse(stdout) {
  const nodes = JSON.parse(stdout).data.search.nodes
  if (!Array.isArray(nodes)) throw new Error('no search nodes')
  // Non-PR search hits come back as empty objects. Drafts go last so they
  // don't push ready PRs out of the capped band (sort is stable).
  return nodes
    .filter((n) => n && typeof n.number === 'number')
    .map(toSegment)
    .sort((a, b) => Number(a.isDraft) - Number(b.isDraft))
}

async function fetchPrs($, org) {
  if (inFlight) return
  inFlight = true
  try {
    const out = await $.process.run([
      'gh', 'api', 'graphql',
      '-f', `q=is:pr is:open author:@me org:${org}`,
      '-f', `query=${QUERY}`,
    ])
    if (out.exitCode !== 0) {
      failed = true
    } else {
      prs = parse(out.stdout)
      failed = false
    }
  } catch {
    failed = true
  } finally {
    inFlight = false
    $.ui.invalidate('ui.render')
  }
}

export function register(on, options) {
  const org = options?.org || 'reserv-technologies'
  const refreshMs = (Number(options?.refreshSeconds) || 120) * 1000

  on('session.start', async ($, e, next) => {
    // First fetch runs on the next tick so startup is not blocked
    $.clock.after(0, () => fetchPrs($, org))
    $.clock.every(refreshMs, () => fetchPrs($, org))
    return next(e)
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    if (!failed && prs.length === 0) return next(e)
    const { Box, Text } = $.ui.resolve(e)
    const theirs = await next(e)

    let row
    if (failed) {
      row = Text({ dimColor: true, children: ['PRs: gh unavailable'] })
    } else {
      // Keep as many segments as fit in the band's width
      const width = Number(e.props?.bodyColumns) || 80
      let used = PREFIX.length
      const parts = [Text({ bold: true, children: [PREFIX] })]
      for (const seg of prs.slice(0, MAX_PRS)) {
        used += SEP.length + seg.text.length
        if (used > width) break
        parts.push(Text({ children: [SEP] }))
        parts.push(Text({ color: seg.color, dimColor: seg.isDraft, children: [seg.text] }))
      }
      row = Box({ flexDirection: 'row', children: parts })
    }

    const children = theirs ? [row, theirs] : [row]
    return Box({ flexDirection: 'column', children })
  })
}
