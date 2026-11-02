// Downloads are created in the browser from data already on the page (Blob URLs): nothing is uploaded.
export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export const downloadText = (text: string, filename: string, type = "application/json") =>
  downloadBlob(new Blob([text], { type }), filename);

export const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "fosit-test";
