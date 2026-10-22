// Minimal Server-Sent-Events parser. Feed it the text received so far; it returns complete events and the unfinished rest.
export function parseSSE(buffer) {
  const blocks = buffer.replace(/\r\n/g, "\n").split("\n\n");
  const rest = blocks.pop();
  const events = [];
  for (const block of blocks) {
    let event = "message";
    const data = [];
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) data.push(line.slice(5).trim());
    }
    if (data.length) {
      try { events.push({ event, data: JSON.parse(data.join("\n")) }); } catch { /* ignore malformed event */ }
    }
  }
  return { events, rest };
}
