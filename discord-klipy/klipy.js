/**
 * Isolated Klipy search → random GIF.
 * Use from a Discord bot (Node 18+ has global fetch).
 * Requires KLIPY_API_KEY in the environment.
 */

const KLIPY_API_KEY = process.env.KLIPY_API_KEY || '';

function pickRandom(items) {
  return items[Math.floor(Math.random() * items.length)];
}

/**
 * @param {string} query
 * @returns {Promise<{ url: string, title: string, id: string | number | null }>}
 */
async function fetchRandomKlipyGif(query) {
  if (!KLIPY_API_KEY) {
    throw new Error('missing KLIPY_API_KEY');
  }
  if (!query || !String(query).trim()) {
    throw new Error('query is required');
  }

  const q = String(query).trim();
  const endpoint = new URL(
    `https://api.klipy.com/api/v1/${KLIPY_API_KEY}/gifs/search`,
  );
  endpoint.searchParams.set('q', q);
  endpoint.searchParams.set('per_page', '20');

  const response = await fetch(endpoint);
  if (!response.ok) {
    throw new Error(`Klipy ${response.status} ${response.statusText}`);
  }

  const body = await response.json();
  const items = body?.data?.data;
  if (!Array.isArray(items) || items.length === 0) {
    throw new Error('no GIF found');
  }

  const item = pickRandom(items);
  const url =
    item?.file?.md?.gif?.url ||
    item?.file?.hd?.gif?.url ||
    item?.file?.sm?.gif?.url;

  if (!url) {
    throw new Error('no GIF URL in response');
  }

  return {
    url,
    title: item.title || q,
    id: item.id ?? null,
  };
}

/**
 * Builds a payload you can pass straight to:
 *   interaction.reply(payload)
 *   message.reply(payload)
 *   channel.send(payload)
 *
 * Uses a raw embed object so this file does not depend on discord.js.
 *
 * @param {string} query
 * @param {{ content?: string }} [options]
 */
async function buildKlipyGifMessage(query, options = {}) {
  const gif = await fetchRandomKlipyGif(query);

  return {
    content: options.content,
    embeds: [
      {
        title: gif.title,
        image: { url: gif.url },
        footer: { text: 'Klipy' },
      },
    ],
  };
}

module.exports = {
  fetchRandomKlipyGif,
  buildKlipyGifMessage,
};
