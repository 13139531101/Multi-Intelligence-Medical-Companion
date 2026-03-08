function iterableToArray(iter) {
  if (
    typeof Symbol !== "undefined" &&
    iter != null &&
    (iter[Symbol.iterator] != null || iter["@@iterator"] != null)
  ) {
    return Array.from(iter);
  }
}

module.exports = iterableToArray;
