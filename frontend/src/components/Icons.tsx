// The static site's inline icons, as components. Decorative: each is aria-hidden,
// and the text beside it carries the meaning.

import type { ReactNode, SVGProps } from 'react'

type IconProps = SVGProps<SVGSVGElement>

function Svg({ children, strokeWidth = 2, ...props }: IconProps & { children: ReactNode }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={strokeWidth}
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false" {...props}>
      {children}
    </svg>
  )
}

export const EyeIcon = (p: IconProps) => (
  <Svg strokeWidth={2.2} {...p}>
    <path d="M1.5 12S5 5.5 12 5.5 22.5 12 22.5 12S19 18.5 12 18.5 1.5 12 1.5 12Z" />
    <circle cx="12" cy="12" r="2.6" />
  </Svg>
)

export const GridIcon = (p: IconProps) => (
  <Svg {...p}>
    <rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" />
    <rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" />
  </Svg>
)

export const FlameIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.07-2.14-.22-4.05 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.15.43-2.29 1-3a2.5 2.5 0 0 0 2.5 2.5z" />
  </Svg>
)

export const PersonIcon = (p: IconProps) => (
  <Svg {...p}><circle cx="12" cy="8" r="4" /><path d="M4 21c0-4.4 3.6-7.5 8-7.5s8 3.1 8 7.5" /></Svg>
)

export const PaperIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 5.5A1.5 1.5 0 0 1 5.5 4h11A1.5 1.5 0 0 1 18 5.5V19a1.5 1.5 0 0 0 1.5 1.5H6A2 2 0 0 1 4 18.5Z" />
    <path d="M18 9h1.5A1.5 1.5 0 0 1 21 10.5V19a1.5 1.5 0 0 1-1.5 1.5" />
    <path d="M7.5 8h7M7.5 11.5h7M7.5 15h4" />
  </Svg>
)

export const SearchIcon = (p: IconProps) => (
  <Svg strokeWidth={2.2} {...p}><circle cx="11" cy="11" r="7" /><path d="m16.5 16.5 4 4" /></Svg>
)

export const InfoIcon = (p: IconProps) => (
  <Svg {...p}><circle cx="12" cy="12" r="9.5" /><path d="M12 11v6M12 7.5v.01" /></Svg>
)

export const OutIcon = (p: IconProps) => (
  <Svg strokeWidth={2.4} {...p}><path d="M7 17 17 7M8 7h9v9" /></Svg>
)

export const ArrowIcon = (p: IconProps) => (
  <Svg strokeWidth={2.4} {...p}><path d="M5 12h14M13 6l6 6-6 6" /></Svg>
)

export const CloseIcon = (p: IconProps) => (
  <Svg strokeWidth={2.4} {...p}><path d="M6 6l12 12M18 6 6 18" /></Svg>
)
