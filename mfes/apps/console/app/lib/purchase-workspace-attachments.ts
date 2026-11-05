/** Local checking only. Server scanning and secure storage remain an integration gate. */
export function checkPurchaseAttachment(file: File, maxBytes: number): Promise<string | null> {
  const extension = file.name.split('.').pop()?.toLowerCase();
  const types: Record<string, string[]> = { pdf: ['application/pdf'], png: ['image/png'], jpg: ['image/jpeg'], jpeg: ['image/jpeg'], webp: ['image/webp'] };
  if (!extension || !types[extension]?.includes(file.type)) return Promise.resolve('Choose a PDF, PNG, JPEG or WebP file with a matching file type.');
  if (file.size === 0 || file.size > maxBytes) return Promise.resolve('The file must be non-empty and within the size limit.');
  return new Promise(resolve => {
    const reader = new FileReader();
    reader.onerror = () => resolve('The file could not be read. Try selecting it again.');
    reader.onload = () => {
      const bytes = new Uint8Array(reader.result as ArrayBuffer);
      const starts = (signature: number[]) => signature.every((byte, index) => bytes[index] === byte);
      const valid = extension === 'pdf' ? starts([37, 80, 68, 70, 45])
        : extension === 'png' ? starts([137, 80, 78, 71, 13, 10, 26, 10])
        : extension === 'webp' ? starts([82, 73, 70, 70]) && [87, 69, 66, 80].every((byte, index) => bytes[index + 8] === byte)
        : starts([255, 216, 255]);
      resolve(valid ? null : 'The file content does not match its declared type. Choose the original document.');
    };
    reader.readAsArrayBuffer(file.slice(0, 12));
  });
}
