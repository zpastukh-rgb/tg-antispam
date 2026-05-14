/**
 * Минимальная проверка цепочки «какой фильтр → какие флаги».
 * Запуск: node webapp/scripts/test_protection_filter_modal_state.mjs
 */
import assert from 'node:assert/strict'
import { protectionFilterModalFlags } from '../src/utils/protectionFilterModalState.js'

const cases = [
  [
    'links',
    {
      showLinksFilterModal: true,
      showMentionsFilterModal: false,
      showMediaFilterModal: false,
      showButtonsFilterModal: false,
      showChannelPostsFilterModal: false,
    },
  ],
  [
    'mentions',
    {
      showLinksFilterModal: false,
      showMentionsFilterModal: true,
      showMediaFilterModal: false,
      showButtonsFilterModal: false,
      showChannelPostsFilterModal: false,
    },
  ],
  [
    'channelPosts',
    {
      showLinksFilterModal: false,
      showMentionsFilterModal: false,
      showMediaFilterModal: false,
      showButtonsFilterModal: false,
      showChannelPostsFilterModal: true,
    },
  ],
]

for (const [which, expected] of cases) {
  assert.deepEqual(protectionFilterModalFlags(which), expected, `flags for ${which}`)
}

console.log('ok: protectionFilterModalFlags', cases.length, 'cases')
