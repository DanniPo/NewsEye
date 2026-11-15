# Site redesign - before and after

The site was simplified on 18 October 2026, after informal feedback that its pages
showed too much at once. Both builds use the same demonstration data (the 16 October
export, 7,339 articles), so the differences come from the page design alone.

- `before-*.png`: the site as built on 16 October.
- `after-*.png`: the site as built on 18 October.
- The number in each file name is the browser width in pixels: 1280 for a laptop,
  390 for a phone.

## Words on screen and page length

Measured on 22 October 2026 in Microsoft Edge through Playwright, with the same
pages opened from both builds. Words are the visible text split on whitespace;
height is the full scrolling height of the page.

| Page | Width | Words before | Words after | Change | Height before | Height after |
|---|---|---|---|---|---|---|
| Dashboard (`index.html`) | 1280 | 888 | 579 | -35% | 2,226 px | 1,497 px |
| Story 903 | 1280 | 1,568 | 944 | -40% | 4,428 px | 3,262 px |
| William Ruto's page | 1280 | 583 | 396 | -32% | 2,195 px | 1,935 px |
| Dashboard | 390 | 880 | 576 | -35% | 4,956 px | 3,350 px |
| Story 903 | 390 | 1,560 | 950 | -39% | 7,030 px | 4,807 px |
| William Ruto's page | 390 | 575 | 393 | -32% | 3,305 px | 2,427 px |

## Opening a story

Clicks from the dashboard to 15 story pages of the redesigned build, opened from
local files in Edge, took a median of 143 ms from the click until the page had
loaded (slowest 199 ms, fastest 94 ms). The pages are built in advance, so
opening one runs no model. This does not include network time on a hosted site.
