def dedup(seq):
  """ Remove duplicates from a sequence, but:

    1. don't change element order
    2. keep the last occurence of each element instead of the first

  Example:
      a = [1, 2, 1, 3, 4, 1, 2, 6, 2]
      b = dedup(a)

  b is now: [3 4 1 6 2]
  """
  out = []
  for e in reversed(seq):
      if e not in out:
          out.insert(0, e)
  return out