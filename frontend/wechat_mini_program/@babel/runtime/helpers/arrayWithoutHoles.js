var arrayLikeToArray = require("./arrayLikeToArray.js");

function arrayWithoutHoles(arr) {
  if (Array.isArray(arr)) return arrayLikeToArray(arr);
}

module.exports = arrayWithoutHoles;
