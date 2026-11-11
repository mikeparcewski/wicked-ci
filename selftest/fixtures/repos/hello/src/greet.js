/** Greets a person by name; an empty or missing name greets "friend". @returns {string} the greeting */
function greet(name) {
  const who = (name || '').trim() || 'friend';
  return `Hello, ${who}!`;
}
module.exports = { greet };
