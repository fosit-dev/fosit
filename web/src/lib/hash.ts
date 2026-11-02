// SHA-256 via the browser's built-in Web Crypto API (no library, nothing sent anywhere).

export async function sha256Hex(data: ArrayBuffer | Uint8Array | string): Promise<string> {
  const bytes = typeof data === "string" ? new TextEncoder().encode(data) : data instanceof Uint8Array ? data : new Uint8Array(data);
  const digest = await crypto.subtle.digest("SHA-256", bytes as BufferSource);
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

/** 8-character uppercase code for humans to read aloud or compare at a glance. */
export const shortCode = (hash: string) => hash.slice(0, 8).toUpperCase();

/** Hash grouped in blocks of 4 for readability. */
export const groupHash = (hash: string) => hash.match(/.{1,4}/g)?.join(" ") ?? hash;
