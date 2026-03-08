var toPrimitive = require("./toPrimitive.js");

function toPropertyKey(arg) {
  var key = toPrimitive(arg, "string");
  return typeof key === "symbol" ? key : String(key);
}

module.exports = toPropertyKey;
