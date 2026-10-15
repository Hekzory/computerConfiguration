// A stdio MCP server with one tool named like a tool lean-harness defers: it must stay untouched.
import readline from 'node:readline'
const send = (msg) => process.stdout.write(JSON.stringify({ jsonrpc: '2.0', ...msg }) + '\n')
const TOOL = { name: 'ScheduleWakeup', description: 'USERKIT-MARKER MCP tool named like the built-in ScheduleWakeup tool.', inputSchema: { type: 'object', properties: {} } }
readline.createInterface({ input: process.stdin }).on('line', (line) => {
  let req
  try {
    req = JSON.parse(line)
  } catch {
    return
  }
  if (req.id === undefined) return
  if (req.method === 'initialize') {
    send({ id: req.id, result: { protocolVersion: req.params?.protocolVersion ?? '2025-06-18', capabilities: { tools: {} }, serverInfo: { name: 'userkit-mcp', version: '0.1.0' } } })
  } else if (req.method === 'tools/list') {
    send({ id: req.id, result: { tools: [TOOL] } })
  } else if (req.method === 'tools/call') {
    send({ id: req.id, result: { content: [{ type: 'text', text: 'ok' }] } })
  } else if (req.method === 'ping') {
    send({ id: req.id, result: {} })
  } else {
    send({ id: req.id, error: { code: -32601, message: `no method ${req.method}` } })
  }
})
