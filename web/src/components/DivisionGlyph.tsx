// One line-drawn mark per division, inline so nothing is fetched at runtime. Drawn on a
// 160-unit square with a shared stroke so the five read as one family.
type Props = { division: string; className?: string };

function Frame({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <svg
      viewBox="0 0 160 160"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={className}
    >
      {children}
    </svg>
  );
}

export function DivisionGlyph({ division, className }: Props) {
  switch (division) {
    case "briech":
      // Quadcopter seen from above: body, four arms, four rotors.
      return (
        <Frame className={className}>
          <rect x="64" y="64" width="32" height="32" rx="3" />
          <path d="M64 64 40 40M96 64l24-24M64 96l-24 24M96 96l24 24" />
          <circle cx="32" cy="32" r="16" />
          <circle cx="128" cy="32" r="16" />
          <circle cx="32" cy="128" r="16" />
          <circle cx="128" cy="128" r="16" />
          <circle cx="80" cy="80" r="4" />
        </Frame>
      );
    case "stratoc":
      // A sensor sweep: range rings, a bearing line and one contact.
      return (
        <Frame className={className}>
          <circle cx="80" cy="80" r="14" />
          <circle cx="80" cy="80" r="34" />
          <circle cx="80" cy="80" r="54" />
          <path d="M80 80 126 34" />
          <circle cx="112" cy="58" r="4" />
          <path d="M80 12v10M80 138v10M12 80h10M138 80h10" />
        </Frame>
      );
    case "giga":
      // A lens over a block of evidence.
      return (
        <Frame className={className}>
          <rect x="22" y="30" width="72" height="88" rx="3" />
          <path d="M36 52h44M36 68h44M36 84h28" />
          <circle cx="100" cy="94" r="30" />
          <path d="m122 116 22 22" />
          <path d="M88 94h24" />
        </Frame>
      );
    case "poctova":
      // A protective shield with a stitched seam.
      return (
        <Frame className={className}>
          <path d="M80 18 128 34v42c0 32-20 54-48 66-28-12-48-34-48-66V34z" />
          <path d="M80 18v124" strokeDasharray="5 6" />
          <path d="M52 66h56M54 96h52" />
        </Frame>
      );
    default:
      // Field Operations: a tent on open ground, a flag and two people.
      return (
        <Frame className={className}>
          <path d="M20 128h120" />
          <path d="M34 128 74 62l40 66" />
          <path d="M74 62v66M74 128 54 128M114 128 94 100" />
          <path d="M122 128V44l22 8-22 8" />
          <circle cx="44" cy="112" r="4" />
          <circle cx="132" cy="112" r="4" />
        </Frame>
      );
  }
}
