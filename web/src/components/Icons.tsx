// Minimal stroke icons, inline so nothing is fetched at runtime.
type P = { size?: number; className?: string };

function Svg({ size = 18, className, children }: P & { children: React.ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={className}
    >
      {children}
    </svg>
  );
}

export const IconUser = (p: P) => (
  <Svg {...p}>
    <circle cx="12" cy="8" r="4" />
    <path d="M4 21c0-4.4 3.6-7 8-7s8 2.6 8 7" />
  </Svg>
);
export const IconLock = (p: P) => (
  <Svg {...p}>
    <rect x="5" y="11" width="14" height="10" rx="1" />
    <path d="M8 11V8a4 4 0 0 1 8 0v3" />
  </Svg>
);
export const IconEye = (p: P) => (
  <Svg {...p}>
    <path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12Z" />
    <circle cx="12" cy="12" r="3" />
  </Svg>
);
export const IconEyeOff = (p: P) => (
  <Svg {...p}>
    <path d="M3 3l18 18M10.6 5.1A10 10 0 0 1 12 5c6.4 0 10 7 10 7a17 17 0 0 1-3.2 4M6.4 6.6A17 17 0 0 0 2 12s3.6 7 10 7a10 10 0 0 0 4-.8M9.9 9.9a3 3 0 0 0 4.2 4.2" />
  </Svg>
);
export const IconChat = (p: P) => (
  <Svg {...p}>
    <path d="M4 5h16v11H9l-5 4V5Z" />
  </Svg>
);
export const IconDashboard = (p: P) => (
  <Svg {...p}>
    <path d="M4 4h7v7H4V4ZM13 4h7v4h-7V4ZM13 11h7v9h-7v-9ZM4 14h7v6H4v-6Z" />
  </Svg>
);
export const IconLog = (p: P) => (
  <Svg {...p}>
    <path d="M6 3h9l4 4v14H6V3Z" />
    <path d="M9 12h7M9 16h7M9 8h3" />
  </Svg>
);
export const IconOrg = (p: P) => (
  <Svg {...p}>
    <rect x="9" y="3" width="6" height="5" />
    <rect x="2" y="16" width="6" height="5" />
    <rect x="9" y="16" width="6" height="5" />
    <rect x="16" y="16" width="6" height="5" />
    <path d="M12 8v4M5 16v-4h14v4" />
  </Svg>
);
export const IconShieldCheck = (p: P) => (
  <Svg {...p}>
    <path d="M12 3 4 6v6c0 5 3.4 8 8 9 4.6-1 8-4 8-9V6l-8-3Z" />
    <path d="m8.5 12 2.5 2.5 4.5-5" />
  </Svg>
);
export const IconShield = (p: P) => (
  <Svg {...p}>
    <path d="M12 3 4 6v6c0 5 3.4 8 8 9 4.6-1 8-4 8-9V6l-8-3Z" />
  </Svg>
);
export const IconClose = (p: P) => (
  <Svg {...p}>
    <path d="M5 5l14 14M19 5 5 19" />
  </Svg>
);
export const IconArrow = (p: P) => (
  <Svg {...p}>
    <path d="M4 12h16M14 6l6 6-6 6" />
  </Svg>
);
export const IconPlus = (p: P) => (
  <Svg {...p}>
    <path d="M12 5v14M5 12h14" />
  </Svg>
);
export const IconLogout = (p: P) => (
  <Svg {...p}>
    <path d="M9 4H4v16h5M16 8l4 4-4 4M20 12H9" />
  </Svg>
);

export const IconMap = (p: P) => (
  <Svg {...p}>
    <path d="M9 4 3 6v14l6-2 6 2 6-2V4l-6 2-6-2ZM9 4v14M15 6v14" />
  </Svg>
);
