/**
 * Чистая логика «какая модалка фильтра открыта» — для тестов и одного места правды.
 * @param {'links'|'mentions'|'media'|'buttons'|'channelPosts'} which
 */
export function protectionFilterModalFlags(which) {
  const w = String(which || '')
  return {
    showLinksFilterModal: w === 'links',
    showMentionsFilterModal: w === 'mentions',
    showMediaFilterModal: w === 'media',
    showButtonsFilterModal: w === 'buttons',
    showChannelPostsFilterModal: w === 'channelPosts',
  }
}
