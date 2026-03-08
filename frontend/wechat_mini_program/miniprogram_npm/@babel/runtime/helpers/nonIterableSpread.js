function nonIterableSpread() {
  throw new TypeError("Invalid attempt to spread non-iterable instance.");
}

module.exports = nonIterableSpread;
