/**
 * Stub Discord command wiring for the Klipy helper.
 *
 * Drop this into a discord.js bot (v14+) and wire `execute` to your
 * command/handler registry. Requires: npm i discord.js
 *
 * Example prefix usage:  !gif cats
 * Example slash option:  /gif query:cats
 */

const { SlashCommandBuilder } = require('discord.js');
const { buildKlipyGifMessage, fetchRandomKlipyGif } = require('./klipy');

// --- Slash command definition (register with your client) ---
const data = new SlashCommandBuilder()
  .setName('gif')
  .setDescription('Send a random Klipy GIF for a keyword')
  .addStringOption((option) =>
    option
      .setName('query')
      .setDescription('Search keyword')
      .setRequired(true),
  );

/**
 * Slash command handler.
 * @param {import('discord.js').ChatInputCommandInteraction} interaction
 */
async function executeSlash(interaction) {
  const query = interaction.options.getString('query', true);

  await interaction.deferReply();

  try {
    const payload = await buildKlipyGifMessage(query);
    await interaction.editReply(payload);
  } catch (error) {
    const message = error?.message || 'failed to fetch GIF';
    await interaction.editReply({ content: `Klipy error: ${message}` });
  }
}

/**
 * Prefix / message-command stub.
 * @param {import('discord.js').Message} message
 * @param {string[]} args  e.g. ['cats'] from "!gif cats"
 */
async function executeMessage(message, args) {
  const query = args.join(' ').trim();
  if (!query) {
    await message.reply('Usage: `!gif <keyword>`');
    return;
  }

  try {
    // Option A — embed reply (recommended)
    const payload = await buildKlipyGifMessage(query);
    await message.reply(payload);

    // Option B — plain URL only (Discord will unfurl the GIF):
    // const { url } = await fetchRandomKlipyGif(query);
    // await message.reply(url);
  } catch (error) {
    const text = error?.message || 'failed to fetch GIF';
    await message.reply(`Klipy error: ${text}`);
  }
}

module.exports = {
  data,
  executeSlash,
  executeMessage,
  // re-export helpers if you prefer calling them from other commands
  buildKlipyGifMessage,
  fetchRandomKlipyGif,
};
