// Shield with an eight-point star, drawn inline (no image assets, no CDN).
export function Emblem({ size = 40 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size * 1.12}
      viewBox="0 0 48 54"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinejoin="round"
      aria-hidden="true"
      className="text-sage"
    >
      <path d="M24 2 5 9v17c0 13 8 21 19 26 11-5 19-13 19-26V9L24 2Z" />
      <path d="M24 12l3.2 9.8L37 25l-9.8 3.2L24 38l-3.2-9.8L11 25l9.8-3.2L24 12Z" />
      <path d="M24 17v16M16 25h16" strokeWidth="1.5" />
    </svg>
  );
}
