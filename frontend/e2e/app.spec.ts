import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

// Font requests go to Google and can fail on a slow network; they are not the app's errors.
const NOISE = /fonts\.(googleapis|gstatic)\.com|ERR_(CONNECTION_)?TIMED_OUT|ERR_SOCKET_NOT_CONNECTED/

function collectErrors(page: Page): string[] {
  const errors: string[] = []
  page.on('console', (message) => {
    if (message.type() === 'error' && !NOISE.test(message.text() + (message.location().url ?? ''))) {
      errors.push(message.text())
    }
  })
  page.on('pageerror', (error) => errors.push(error.message))
  return errors
}

async function sideways(page: Page): Promise<number> {
  return page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
}

test('the dashboard opens on the new headline and the sources, with no snapshot', async ({ page }) => {
  const errors = collectErrors(page)
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1 })).toContainText('newsrooms.')
  const sources = page.getByRole('region', { name: 'Our sources' })
  await expect(sources.locator('.srcchips a')).toHaveCount(12)
  await expect(page.locator('body')).not.toContainText(/snapshot|data as of/i)
  await expect(page.locator('.tile').first()).toBeVisible()
  expect(await sideways(page)).toBe(0)
  expect(errors).toEqual([])
})

test('a reader goes from a story card to the story, its facts and an outlet', async ({ page }) => {
  const errors = collectErrors(page)
  await page.goto('/')
  const card = page.locator('.tile').first()
  const title = (await card.locator('h3').textContent())!.trim()
  await card.click()
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(title)
  await page.getByRole('tab', { name: /Facts/ }).click()
  await expect(page).toHaveURL(/#facts$/)
  await expect(page.getByRole('tabpanel')).toBeVisible()
  const outlet = page.locator('aside.side a.olink').first()
  const name = (await outlet.textContent())!.trim()
  await outlet.click()
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(name)
  await expect(page.locator('.heads li').first()).toBeVisible()
  expect(errors).toEqual([])
})

test('the browser animates page changes with view transitions, without errors', async ({ page }) => {
  const errors = collectErrors(page)
  await page.goto('/')
  expect(await page.evaluate(() => 'startViewTransition' in document)).toBe(true)
  await expect(page.locator('.tile').first()).toBeVisible()
  // re-ordering the list runs a transition over every card at once: any two
  // elements sharing a transition name would be reported as an error here
  await page.getByRole('button', { name: 'Most differences' }).click()
  await expect(page).toHaveURL(/sort=differences/)
  await page.getByRole('button', { name: 'Latest', exact: true }).click()
  await expect(page).toHaveURL(/sort=latest/)
  await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Sources' }).click()
  await expect(page.getByRole('heading', { name: 'Where the news comes from' })).toBeVisible()
  await page.getByRole('button', { name: 'A to Z' }).click()
  await expect(page.locator('.srccard h3').first()).toHaveText('Amref Newsroom')
  await page.locator('.srccard').first().click()
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Amref Newsroom')
  expect(errors).toEqual([])
})

test('with reduced motion, the headline does not move', async ({ browser }) => {
  const context = await browser.newContext({ reducedMotion: 'reduce' })
  const page = await context.newPage()
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(/See how each one tells it\./)
  await expect(page.locator('.rot')).toHaveCount(0)
  await context.close()
})

test('search finds articles by meaning and links to their stories', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('searchbox', { name: /Search every article/ }).fill('housing levy')
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(/\/search\?q=housing\+levy/)
  await expect(page.locator('.hit').first()).toBeVisible({ timeout: 45_000 })
  await expect(page.getByText(/close in meaning to “housing levy”/)).toBeVisible()
})

test('people: the list, then one person outlet by outlet', async ({ page }) => {
  await page.goto('/people')
  await page.locator('table.ptable a.nm').first().click()
  await expect(page.getByRole('heading', { name: 'Outlet by outlet' })).toBeVisible()
  await expect(page.locator('table.glance tbody tr').first()).toBeVisible()
})

test('on a phone, no page scrolls sideways', async ({ browser }) => {
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } })
  for (const path of ['/', '/sources', '/sources/people-daily', '/people', '/contested']) {
    await page.goto(path)
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    expect(await sideways(page), path).toBe(0)
  }
  await page.goto('/')
  await page.locator('.tile').first().click()
  for (const tab of ['Facts', 'Quotes', 'Numbers']) {
    const button = page.getByRole('tab', { name: new RegExp(tab) })
    if (await button.count()) {
      await button.click()
      await page.waitForTimeout(500)
      expect(await sideways(page), tab).toBe(0)
    }
  }
  await page.close()
})

test('an unknown story says so inside the frame', async ({ page }) => {
  await page.goto('/stories/999999')
  await expect(page.getByRole('heading', { name: 'We could not find that' })).toBeVisible()
  await expect(page.getByRole('navigation', { name: 'Main' })).toBeVisible()
})
