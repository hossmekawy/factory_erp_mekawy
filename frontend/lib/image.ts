// Shrink a camera photo before upload. SRS section 10 caps stored images at
// 1MB; a modern phone camera produces 4-8MB, and the supervisor is often on
// mobile data in the hall.
//
// Canvas only — no library.

const MAX_EDGE = 1600;
const TARGET_BYTES = 1024 * 1024;

export async function compressImage(file: File, maxBytes = TARGET_BYTES): Promise<File> {
  if (!file.type.startsWith("image/")) return file;

  const bitmap = await createImageBitmap(file).catch(() => null);
  if (!bitmap) return file; // unsupported format — send it as it came

  const scale = Math.min(1, MAX_EDGE / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  const ctx = canvas.getContext("2d");
  if (!ctx) return file;
  ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close?.();

  // Step the quality down until it fits; a notebook page is mostly white, so
  // this usually lands on the first try.
  for (const quality of [0.82, 0.7, 0.6, 0.5, 0.4]) {
    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, "image/jpeg", quality)
    );
    if (!blob) break;
    if (blob.size <= maxBytes || quality === 0.4) {
      return new File([blob], renameToJpg(file.name), {
        type: "image/jpeg",
        lastModified: Date.now(),
      });
    }
  }
  return file;
}

function renameToJpg(name: string): string {
  return name.replace(/\.[^.]+$/, "") + ".jpg";
}
