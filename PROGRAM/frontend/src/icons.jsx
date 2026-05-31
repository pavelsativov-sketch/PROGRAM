import React from 'react';

/**
 * Botanical line icons. Все одного штриха (1.6px), strokeLinecap=round.
 * Заменяет эмодзи в навигации, статусах и пр. — даёт единый «не-ИИ» стиль.
 */

const Svg = ({ children, size = 18, ...rest }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.6"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
    {...rest}
  >
    {children}
  </svg>
);

export const IconHome = (p) => (
  <Svg {...p}><path d="M3 11.5 12 4l9 7.5" /><path d="M5 10v10h14V10" /></Svg>
);
export const IconFlow = (p) => (
  <Svg {...p}><circle cx="6" cy="6" r="2.2" /><circle cx="18" cy="6" r="2.2" /><circle cx="12" cy="18" r="2.2" /><path d="M7.5 7.5 11 16M16.5 7.5 13 16" /></Svg>
);
export const IconChat = (p) => (
  <Svg {...p}><path d="M4 5h16v11H8l-4 4z" /><path d="M8 9h8M8 12h5" /></Svg>
);
export const IconBag = (p) => (
  <Svg {...p}><path d="M5 8h14l-1 12H6z" /><path d="M9 8a3 3 0 0 1 6 0" /></Svg>
);
export const IconLeaf = (p) => (
  <Svg {...p}><path d="M5 19c0-9 5-14 14-14 0 9-5 14-14 14z" /><path d="M5 19 12 12" /></Svg>
);
export const IconBouquet = (p) => (
  <Svg {...p}><circle cx="9" cy="6" r="2.5" /><circle cx="15" cy="6" r="2.5" /><circle cx="12" cy="9.5" r="2.3" /><path d="M12 11v9M9 14l3 4M15 14l-3 4" /></Svg>
);
export const IconSparkle = (p) => (
  <Svg {...p}><path d="M12 4v6M12 14v6M4 12h6M14 12h6" /><path d="m6.5 6.5 2.5 2.5M14.5 14.5l2.5 2.5M6.5 17.5l2.5-2.5M14.5 9.5l2.5-2.5" /></Svg>
);
export const IconWrench = (p) => (
  <Svg {...p}><path d="M14 7a4 4 0 0 0-5.66 5.66L4 17l3 3 4.34-4.34A4 4 0 0 0 17 10" /></Svg>
);
export const IconUsers = (p) => (
  <Svg {...p}><circle cx="9" cy="8" r="3.2" /><path d="M3 19c0-3 2.5-5 6-5s6 2 6 5" /><path d="M16 11a3 3 0 0 0 0-6" /><path d="M21 19c0-2.5-2-4.5-5-5" /></Svg>
);
export const IconLogout = (p) => (
  <Svg {...p}><path d="M14 4h4v16h-4" /><path d="M10 8 6 12l4 4M6 12h10" /></Svg>
);
export const IconWhatsapp = (p) => (
  <Svg {...p}><path d="M3 21l1.6-5.2A8 8 0 1 1 9 19l-6 2z" /><path d="M9 9c0 4 3 6 6 6l1.5-1.5L14 12.5l-1 1c-1 0-2.5-1.5-2.5-2.5l1-1L10 9z" /></Svg>
);
export const IconInstagram = (p) => (
  <Svg {...p}><rect x="3.5" y="3.5" width="17" height="17" rx="4.5" /><circle cx="12" cy="12" r="3.8" /><circle cx="17" cy="7" r="0.6" fill="currentColor" /></Svg>
);
export const IconLab = (p) => (
  <Svg {...p}><path d="M9 4h6M10 4v7l-5 8a1 1 0 0 0 .9 1.5h12.2A1 1 0 0 0 19 19l-5-8V4" /></Svg>
);
export const IconPrinter = (p) => (
  <Svg {...p}><rect x="6" y="13" width="12" height="7" rx="1" /><path d="M6 13V5h12v8" /><path d="M9 17h6" /></Svg>
);
export const IconPhone = (p) => (
  <Svg {...p}><path d="M5 4h3l1.5 4-2 1.5a11 11 0 0 0 7 7L16 14.5 20 16v3a2 2 0 0 1-2.2 2A16 16 0 0 1 3 6.2 2 2 0 0 1 5 4z" /></Svg>
);
export const IconChevron = (p) => (
  <Svg {...p}><path d="m9 6 6 6-6 6" /></Svg>
);
export const IconCheck = (p) => (
  <Svg {...p}><path d="m5 12 4 4 10-10" /></Svg>
);
export const IconClose = (p) => (
  <Svg {...p}><path d="M6 6l12 12M6 18 18 6" /></Svg>
);
export const IconCalendar = (p) => (
  <Svg {...p}><rect x="3.5" y="5" width="17" height="15" rx="2" /><path d="M3.5 9h17M8 3v4M16 3v4" /></Svg>
);
export const IconNote = (p) => (
  <Svg {...p}><path d="M5 4h11l3 3v13H5z" /><path d="M9 9h6M9 13h6M9 17h4" /></Svg>
);
