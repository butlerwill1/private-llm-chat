/** Decode UTF-8 and NDJSON independently of network chunk boundaries. */
export async function* streamLines(body: ReadableStream<Uint8Array>): AsyncGenerator<string> {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  try {
    while (true) {
      const { value, done } = await reader.read()
      buffer += decoder.decode(value, { stream: !done })
      let boundary: number
      while ((boundary = buffer.indexOf('\n')) !== -1) {
        const line = buffer.slice(0, boundary).trim()
        buffer = buffer.slice(boundary + 1)
        if (line) yield line
      }
      if (done) break
    }
    if (buffer.trim()) yield buffer.trim()
  } finally {
    await reader.cancel().catch(() => undefined)
    reader.releaseLock()
  }
}
