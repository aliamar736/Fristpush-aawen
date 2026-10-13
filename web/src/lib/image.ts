/** Client-side compression before upload (saves data on weak connections). Server re-encodes & strips EXIF too. */
export async function compressImage(file: Blob, maxSide = 1600, quality = 0.78): Promise<Blob> {
  if (!file.type.startsWith("image/")) return file;
  try {
    const bmp = await createImageBitmap(file);
    const scale = Math.min(1, maxSide / Math.max(bmp.width, bmp.height));
    const w = Math.round(bmp.width * scale);
    const h = Math.round(bmp.height * scale);
    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    canvas.getContext("2d")!.drawImage(bmp, 0, 0, w, h);
    const out: Blob | null = await new Promise((res) => canvas.toBlob(res, "image/jpeg", quality));
    return out && out.size < file.size ? out : file;
  } catch {
    return file; // decoding unsupported — let the server handle it
  }
}
