function arrayLikeToArray(arr, len) {
  if (len == null || len > arr.length) len = arr.length;
  var arr2 = new Array(len);
  for (var i = 0; i < len; i += 1) arr2[i] = arr[i];
  return arr2;
}

function arrayWithoutHoles(arr) {
  if (Array.isArray(arr)) return arrayLikeToArray(arr);
}

module.exports = arrayWithoutHoles;
