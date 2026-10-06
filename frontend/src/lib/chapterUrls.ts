// REQ-005/011: a single {n} cannot advance two separate chapter identifiers.
export function hasAmbiguousChapterIds(template: string | null): boolean {
  if (!template) return false
  try {
    const url = new URL(template)
    const pathHasChapter = /(?:chapter|chap|ch|episode|ep)[-_.]?(?:\{n\}|\d+)/i.test(url.pathname)
    const queryHasChapter = ['episode_no', 'chapter_no', 'ep_no', 'episode', 'chapter', 'ep', 'ch']
      .some((name) => url.searchParams.has(name))
    return pathHasChapter && queryHasChapter
  } catch { return false }
}
