/** JSON.parse rejects malformed input; this additionally rejects duplicate object members. */
export function strictJson(text: string): unknown {
  const value: unknown = JSON.parse(text);
  const objects: (Set<string> | null)[] = [];
  for (let index = 0; index < text.length; index++) {
    const character = text[index];
    if (character === '{') objects.push(new Set());
    else if (character === '[') objects.push(null);
    else if (character === '}' || character === ']') objects.pop();
    else if (character === '"') {
      const start = index++;
      while (index < text.length && text[index] !== '"') {
        if (text[index] === '\\') index++;
        index++;
      }
      let next = index + 1;
      while (/\s/.test(text[next] ?? '') && next < text.length) next++;
      if (text[next] === ':') {
        const members = objects.at(-1), name: string = JSON.parse(text.slice(start, index + 1));
        if (!members || members.has(name)) throw new SyntaxError('Duplicate JSON field');
        members.add(name);
      }
    }
  }
  return value;
}
