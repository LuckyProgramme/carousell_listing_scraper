"use client";

import { ImageOff } from "lucide-react";
import { useState } from "react";

export function ListingThumbnail({ src, title }: { src: string | null; title: string }) {
  const [failed, setFailed] = useState(false);

  if (!src || failed) {
    return <div className="thumbnail-fallback" role="img" aria-label={`No thumbnail available for ${title}`}><ImageOff aria-hidden="true" /><span>Image unavailable</span></div>;
  }

  // Carousell hosts the source image; no image bytes are copied into Supabase.
  // eslint-disable-next-line @next/next/no-img-element
  return <img className="listing-thumbnail" src={src} alt={`Carousell listing: ${title}`} loading="lazy" referrerPolicy="no-referrer" onError={() => setFailed(true)} />;
}
