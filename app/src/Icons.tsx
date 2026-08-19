// Iconos de trazo propios. No usamos emojis porque cada sistema los dibuja distinto
// (y en Windows salen a color, que rompe la interfaz plana).
const P = { fill: "none", stroke: "currentColor", strokeWidth: 1.7, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };

type Props = { size?: number; className?: string };
const box = (size: number, className?: string) => ({
  width: size, height: size, viewBox: "0 0 24 24", className, "aria-hidden": true,
});

export const IconFilm = ({ size = 18, className }: Props) => (
  <svg {...box(size, className)}><g {...P}>
    <rect x="2.5" y="4" width="19" height="16" rx="2" />
    <path d="M7 4v16M17 4v16M2.5 12h19M2.5 8h4.5M2.5 16h4.5M17 8h4.5M17 16h4.5" />
  </g></svg>
);

export const IconBrand = ({ size = 18, className }: Props) => (
  <svg {...box(size, className)}><g {...P}>
    <path d="M12 3a9 9 0 1 0 0 18c1.1 0 1.7-.9 1.4-1.7-.4-1 .3-2 1.4-2H17a4 4 0 0 0 4-4c0-5-4-10-9-10z" />
    <circle cx="7.5" cy="12" r="1.2" /><circle cx="10" cy="7.5" r="1.2" /><circle cx="15" cy="8" r="1.2" />
  </g></svg>
);

export const IconClock = ({ size = 18, className }: Props) => (
  <svg {...box(size, className)}><g {...P}>
    <circle cx="12" cy="12" r="9" /><path d="M12 7v5l3.2 2" />
  </g></svg>
);

export const IconSliders = ({ size = 18, className }: Props) => (
  <svg {...box(size, className)}><g {...P}>
    <path d="M4 7h10M18 7h2M4 17h4M12 17h8" />
    <circle cx="16" cy="7" r="2.2" /><circle cx="10" cy="17" r="2.2" />
  </g></svg>
);

export const IconFolder = ({ size = 18, className }: Props) => (
  <svg {...box(size, className)}><g {...P}>
    <path d="M3 7a2 2 0 0 1 2-2h3.4a2 2 0 0 1 1.5.7l1 1.3H19a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
  </g></svg>
);

export const IconChevron = ({ size = 18, className }: Props) => (
  <svg {...box(size, className)}><g {...P}><path d="M6 9l6 6 6-6" /></g></svg>
);

export const IconDrop = ({ size = 18, className }: Props) => (
  <svg {...box(size, className)}><g {...P}>
    <path d="M12 3v11m0 0l-4-4m4 4l4-4M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" />
  </g></svg>
);

export const IconScissors = ({ size = 18, className }: Props) => (
  <svg {...box(size, className)}><g {...P}>
    <circle cx="6" cy="18" r="2.6" /><circle cx="6" cy="6" r="2.6" />
    <path d="M8 7.5L20 18M20 6L8 16.5" />
  </g></svg>
);

export const IconMic = ({ size = 18, className }: Props) => (
  <svg {...box(size, className)}><g {...P}>
    <rect x="9" y="2.5" width="6" height="11" rx="3" />
    <path d="M5.5 11.5a6.5 6.5 0 0 0 13 0M12 18v3.5" />
  </g></svg>
);

export const IconZap = ({ size = 18, className }: Props) => (
  <svg {...box(size, className)}><g {...P}>
    <path d="M13.5 2.5L4 13.5h6.5L10.5 21.5 20 10.5h-6.5z" />
  </g></svg>
);

export const IconCaptions = ({ size = 18, className }: Props) => (
  <svg {...box(size, className)}><g {...P}>
    <rect x="2.5" y="5" width="19" height="14" rx="2.5" />
    <path d="M9 10.5a2.5 2.5 0 1 0 0 3M17 10.5a2.5 2.5 0 1 0 0 3" />
  </g></svg>
);

export const IconCheck = ({ size = 18, className }: Props) => (
  <svg {...box(size, className)}><g {...P}><path d="M5 12.5l4.5 4.5L19 7" /></g></svg>
);

export const IconSpark = ({ size = 18, className }: Props) => (
  <svg {...box(size, className)}><g {...P}><path d="M12 3l2 6 6 2-6 2-2 6-2-6-6-2 6-2z" /></g></svg>
);

export const IconPlay = ({ size = 18, className }: Props) => (
  <svg {...box(size, className)}><g {...P}><path d="M7 4.5l12 7.5-12 7.5z" /></g></svg>
);

export const IconVideo = ({ size = 18, className }: Props) => (
  <svg {...box(size, className)}><g {...P}>
    <rect x="2.5" y="6" width="13" height="12" rx="2" /><path d="M15.5 10.5l6-3.5v10l-6-3.5z" />
  </g></svg>
);

// El cuadrado de parar, el mismo que lleva cualquier reproductor. Un icono que
// ya conoces no hay que explicarlo.
export const IconStop = ({ size = 18, className }: Props) => (
  <svg {...box(size, className)}><g {...P}>
    <rect x="6" y="6" width="12" height="12" rx="2" />
  </g></svg>
);

export const IconAlert = ({ size = 18, className }: Props) => (
  <svg {...box(size, className)}><g {...P}>
    <circle cx="12" cy="12" r="9" /><path d="M12 7.5v5.5M12 16.2v.3" />
  </g></svg>
);

export const IconRefresh = ({ size = 18, className }: Props) => (
  <svg {...box(size, className)}><g {...P}>
    <path d="M20 11a8 8 0 1 0-.7 4.5" /><path d="M20 5.5V11h-5.5" />
  </g></svg>
);

export const IconUndo = ({ size = 18, className }: Props) => (
  <svg {...box(size, className)}><g {...P}>
    <path d="M4 11a8 8 0 1 1 .7 4.5" /><path d="M4 5.5V11h5.5" />
  </g></svg>
);

export const IconKey = ({ size = 18, className }: Props) => (
  <svg {...box(size, className)}><g {...P}>
    <circle cx="8" cy="12" r="4.2" /><path d="M12.2 12H21M18 12v3M15.5 12v2.2" />
  </g></svg>
);

export const IconPlug = ({ size = 18, className }: Props) => (
  <svg {...box(size, className)}><g {...P}>
    <path d="M9 3v6M15 3v6M6.5 9h11v3a5.5 5.5 0 0 1-11 0zM12 17.5V21" />
  </g></svg>
);

export const IconBook = ({ size = 18, className }: Props) => (
  <svg {...box(size, className)}><g {...P}>
    <path d="M4 4.5A1.5 1.5 0 0 1 5.5 3H19v14.5H5.5A1.5 1.5 0 0 0 4 19z" /><path d="M4 19a1.5 1.5 0 0 0 1.5 1.5H19" />
  </g></svg>
);

export const IconFolderOpen = ({ size = 18, className }: Props) => (
  <svg {...box(size, className)}><g {...P}>
    <path d="M3 7a2 2 0 0 1 2-2h3.4a2 2 0 0 1 1.5.7l1 1.3H19a2 2 0 0 1 2 2v1H3z" />
    <path d="M3 10h18l-2 8a1.5 1.5 0 0 1-1.4 1H5.4A1.5 1.5 0 0 1 4 18z" />
  </g></svg>
);
