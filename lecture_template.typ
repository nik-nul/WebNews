#let r = json("lecture_latest.json")

#let data = r.at("data")
#let due = r.at("due")

#let date = data.at("date")
#let no = data.at("no")
#let saying = data.at("saying", default: "謹言慎行")
#let loc = data.at("loc", default: "南京市栖霞区")
#let ncols = calc.max(1, calc.min(8, int(data.at("columns", default: 4))))

#let lecture = data.at("lecture")
#let other = data.at("other")
#let college = data.at("college")
#let club = data.at("club")

#let lecture-due = due.at("lecture")
#let other-due = due.at("other")
#let college-due = due.at("college")
#let club-due = due.at("club")

#import "@preview/tiaoma:0.3.0"
#import "@preview/wrap-it:0.1.1"

#set page(
  height: auto,
  width: 9in + (ncols - 2) * (3.42in + 0.8in + 0.5in),
  margin: (left: 0.9in, right: 0.9in, top: 0.7in, bottom: 0.7in)
)

#let due-row-cells(e) = (
  if e.at("link") != none {
    link(e.at("link"))[#e.at("title")]
  } else {
    e.at("title")
  },
  [#e.at("due_time").slice(5, 10)],
  [#link("https://nik-nul.github.io/news/" + e.at("publish_date").slice(0, 10),
         e.at("publish_date").slice(5, 10))],
)
#let with-narrow(narrow, body) = if narrow {
  [#show table.cell.where(x: 0): set text(size: 0.78em)
   #show table.cell.where(x: 0, y: 0): set text(size: (1/0.78) * 1em)
   #body]
} else { [#body] }
#let due-table(rows, narrow) = with-narrow(narrow, table(
  columns: (auto, auto, auto),
  align: (center + horizon, center + horizon, center + horizon),
  stroke: 1pt,
  table.header([*活动*], [*截止时间*], [*刊载时间*]),
  ..for e in rows { due-row-cells(e) },
))

#let stub-numbering = (..nums) => if nums.pos().len() > 1 { "88.88." } else { "88." }
#let measure-bodies(cw, bodies) = {
  range(bodies.len()).map(i => {
    measure(block(width: cw, { set heading(numbering: stub-numbering); bodies.at(i) })).height
  })
}
#let measure-chunk(cw, rows, narrow, list-title, cnt, off, first) = {
  if cnt == 0 { 0pt } else {
    let t = due-table(rows.slice(off, off + cnt), narrow)
    let body = if first and list-title != none { heading(level: 2)[#list-title] + t } else { t }
    measure(block(width: cw, body)).height
  }
}
#let fit-rows(cw, rows, narrow, list-title, first, pos, k, budget, force-min) = {
  let remain = k - pos
  if remain <= 0 { return (0, 0pt) }
  if budget < 0pt and not force-min { return (0, 0pt) }
  let meas = m => measure-chunk(cw, rows, narrow, list-title, m, pos, first)
  let lo = 0
  let hi = remain
  let h-lo = 0pt
  while lo < hi {
    let mid = lo + calc.quo(hi - lo + 1, 2)
    let h = meas(mid)
    if h <= budget { lo = mid; h-lo = h } else { hi = mid - 1 }
  }
  if force-min and lo == 0 {
    lo = 1
    h-lo = meas(1)
  }
  (lo, h-lo)
}
#let break-limit = 240pt
#let wrap-bodies(bodies, hs) = range(bodies.len()).map(i => {
  if hs.at(i) > break-limit { bodies.at(i) } else { block(breakable: false, width: 100%, bodies.at(i)) }
})
#let pack-tiers(n, hs, pris) = {
  let infos = range(hs.len()).map(i => (idx: i, pri: pris.at(i), h: hs.at(i)))
  let sorted = infos.sorted(key: x => (-x.pri, -x.h))
  let k0 = calc.min(n - 1, sorted.len())
  let tiers = ()
  tiers.push(sorted.slice(0, k0).sorted(key: x => -x.h).map(x => x.idx))
  let rest = sorted.slice(k0)
  let t = 0
  while t < rest.len() {
    tiers.push(rest.slice(t, calc.min(t + n, rest.len())).sorted(key: x => -x.h).map(x => x.idx))
    t += n
  }
  tiers
}
#let table-allowed(n, counts) = {
  let last = -1
  for c in range(n) {
    if counts.at(c) > 0 { last = c }
  }
  range(n).map(c => if last < 0 { true } else { if counts.at(c) == 0 { true } else { c == last } })
}
#let pack-new-cols(n) = (range(n).map(_ => 0pt), range(n).map(_ => ()), range(n).map(_ => ()))
#let pack-tier0(n, tier0, hs, col-loads, allowed: none) = {
  let (col-h, col-idx, col-tier) = pack-new-cols(n)
  for c in range(n) { col-h.at(c) = col-loads.at(c) }
  for idx in tier0 {
    let best = -1
    for c in range(1, n) {
      if allowed == none or allowed.at(c) {
        if best == -1 or col-h.at(c) < col-h.at(best) { best = c }
      }
    }
    if best == -1 {
      for c in range(n) {
        if allowed == none or allowed.at(c) {
          if best == -1 or col-h.at(c) < col-h.at(best) { best = c }
        }
      }
    }
    if best != -1 {
      col-idx.at(best).push(idx)
      col-tier.at(best).push(0)
      col-h.at(best) = col-h.at(best) + hs.at(idx)
    }
  }
  (col-h, col-idx, col-tier)
}
#let pack-lpt-rest(n, rest-tiers, hs, st, allowed: none) = {
  let (col-h, col-idx, col-tier) = st
  let tier-no = 1
  for tier in rest-tiers {
    for idx in tier {
      let best = -1
      for c in range(n) {
        if allowed == none or allowed.at(c) {
          if best == -1 or col-h.at(c) < col-h.at(best) { best = c }
        }
      }
      if best != -1 {
        col-idx.at(best).push(idx)
        col-tier.at(best).push(tier-no)
        col-h.at(best) = col-h.at(best) + hs.at(idx)
      }
    }
    tier-no += 1
  }
  (col-h, col-idx, col-tier)
}
#let pack-ffd-rest(n, rest-tiers, hs, C, st, allowed: none) = {
  let (col-h, col-idx, col-tier) = st
  let ok = true
  let tier-no = 1
  for tier in rest-tiers {
    for idx in tier {
      let h = hs.at(idx)
      let placed = false
      for c in range(n) {
        if (not placed) and (allowed == none or allowed.at(c)) and col-h.at(c) + h <= C {
          col-h.at(c) = col-h.at(c) + h
          col-idx.at(c).push(idx)
          col-tier.at(c).push(tier-no)
          placed = true
        }
      }
      if not placed { ok = false }
    }
    tier-no += 1
  }
  (ok, (col-h, col-idx, col-tier))
}
#let pack-max(col-h) = {
  let M = 0pt
  for h in col-h {
    if h > M { M = h }
  }
  M
}
#let enforce-min-blank(n, st, hs, pris, max-blank-ratio: 0.2) = {
  let (col-h, col-idx, col-tier) = st
  let M = pack-max(col-h)
  let floor = M * (1 - max-blank-ratio)
  for _sweep in range(6) {
    let cur-min = col-h.fold(M, calc.min)
    if cur-min >= floor { break }
    let s = 0
    for c in range(1, n) {
      if col-h.at(c) < col-h.at(s) { s = c }
    }
    let best-d = 0pt
    let best-t = -1
    let best-ps = -1
    let best-pt = -1
    let best-il = -1
    let best-ir = -1
    for ps in range(col-idx.at(s).len()) {
      let il = col-idx.at(s).at(ps)
      let pr = pris.at(il)
      let hl = hs.at(il)
      for t in range(n) {
        if t == s { continue }
        for pt in range(col-idx.at(t).len()) {
          let ir = col-idx.at(t).at(pt)
          if pris.at(ir) != pr { continue }
          let hr = hs.at(ir)
          if hr <= hl { continue }
          let new-s = col-h.at(s) - hl + hr
          let new-t = col-h.at(t) - hr + hl
          if new-s > M or new-t > M { continue }
          let nmn = new-s
          if new-t < nmn { nmn = new-t }
          for q in range(n) {
            if q != s and q != t and col-h.at(q) < nmn { nmn = col-h.at(q) }
          }
          if nmn > cur-min and (best-t == -1 or nmn > cur-min + best-d) {
            best-d = nmn - cur-min
            best-t = t
            best-ps = ps
            best-pt = pt
            best-il = il
            best-ir = ir
          }
        }
      }
    }
    if best-t == -1 { break }
    let coll = col-idx.at(s)
    coll.at(best-ps) = best-ir
    col-idx.at(s) = coll
    let colr = col-idx.at(best-t)
    colr.at(best-pt) = best-il
    col-idx.at(best-t) = colr
    let hl = hs.at(best-il)
    let hr = hs.at(best-ir)
    col-h.at(s) = col-h.at(s) - hl + hr
    col-h.at(best-t) = col-h.at(best-t) - hr + hl
  }
  (col-h, col-idx, col-tier)
}
#let left-pack-table(n, rows, narrow, cw, list-title, counts, chunks, col-h) = {
  let k = rows.len()
  if k == 0 { return (counts, chunks, col-h, range(n).map(_ => 0pt)) }
  let M = pack-max(col-h)
  let build = (cnt, off, first) => {
    if cnt == 0 { none } else {
      let t = due-table(rows.slice(off, off + cnt), narrow)
      if first and list-title != none { heading(level: 2)[#list-title] + t } else { t }
    }
  }
  let meas = (cnt, off, first) => {
    if cnt == 0 { 0pt } else { measure(block(width: cw, build(cnt, off, first))).height }
  }
  let offs = ()
  let acc = 0
  for c in range(n) {
    offs.push(acc)
    acc += counts.at(c)
  }
  let ch = range(n).map(c => meas(counts.at(c), offs.at(c), c == 0))
  for c in range(1, n) {
    while counts.at(c) > 0 {
      let nd = counts.at(c - 1) + 1
      let ns = counts.at(c) - 1
      let hd-new = meas(nd, offs.at(c - 1), c - 1 == 0)
      if col-h.at(c - 1) - ch.at(c - 1) + hd-new > M { break }
      let hs-new = meas(ns, offs.at(c) + 1, false)
      counts.at(c - 1) = nd
      counts.at(c) = ns
      col-h.at(c - 1) = col-h.at(c - 1) - ch.at(c - 1) + hd-new
      col-h.at(c) = col-h.at(c) - ch.at(c) + hs-new
      ch.at(c - 1) = hd-new
      ch.at(c) = hs-new
      offs.at(c) = offs.at(c) + 1
    }
  }
  let chunks2 = ()
  let pos = 0
  for c in range(n) {
    let cnt = counts.at(c)
    chunks2.push(build(cnt, pos, c == 0))
    pos += cnt
  }
  (counts, chunks2, col-h, ch)
}
#let balance-table-cols(n, rows, narrow, cw, list-title, H0, counts, msg_sums, max-iters: 30) = {
  let k = rows.len()
  let last = -1
  for c in range(n) {
    if counts.at(c) > 0 { last = c }
  }
  if k == 0 or last < 1 { return (counts, range(n).map(_ => none), range(n).map(_ => 0pt)) }
  let build = (cnt, off, first) => {
    if cnt == 0 { none } else {
      let t = due-table(rows.slice(off, off + cnt), narrow)
      if first and list-title != none { heading(level: 2)[#list-title] + t } else { t }
    }
  }
  let meas = (cnt, off, first) => {
    if cnt == 0 { 0pt } else { measure(block(width: cw, build(cnt, off, first))).height }
  }
  let offs-of(cs) = {
    let o = ()
    let a = 0
    for c in range(n) {
      o.push(a)
      a += cs.at(c)
    }
    o
  }
  let offs = offs-of(counts)
  let ch = range(n).map(c => meas(counts.at(c), offs.at(c), c == 0))
  let totals = range(n).map(c => (if c == 0 { H0 } else { 0pt }) + ch.at(c) + msg_sums.at(c))
  let cur-max = totals.fold(0pt, calc.max)
  let rebuild(cs) = {
    let o = offs-of(cs)
    let cks = ()
    let hs = ()
    for c in range(n) {
      cks.push(build(cs.at(c), o.at(c), c == 0))
      hs.push(meas(cs.at(c), o.at(c), c == 0))
    }
    (cks, hs)
  }
  for _it in range(max-iters) {
    let best-d = 0pt
    let best-c = -1
    let best-dir = 0
    let best-h0 = 0pt
    let best-h1 = 0pt
    for c in range(last) {
      if counts.at(c) > 0 and counts.at(c + 1) > 0 {
        if counts.at(c) > 1 {
          let nc0 = counts.at(c) - 1
          let nc1 = counts.at(c + 1) + 1
          let noff1 = offs.at(c + 1) - 1
          let h0-new = meas(nc0, offs.at(c), c == 0)
          let h1-new = meas(nc1, noff1, false)
          let t0-new = (if c == 0 { H0 } else { 0pt }) + h0-new + msg_sums.at(c)
          let t1-new = h1-new + msg_sums.at(c + 1)
          let nmx = t0-new
          if t1-new > nmx { nmx = t1-new }
          for q in range(n) {
            if q != c and q != c + 1 and totals.at(q) > nmx { nmx = totals.at(q) }
          }
          if nmx < cur-max and (best-c == -1 or nmx < cur-max - best-d) {
            best-d = cur-max - nmx
            best-c = c
            best-dir = -1
            best-h0 = h0-new
            best-h1 = h1-new
          }
        }
        if counts.at(c + 1) > 1 {
          let nc0 = counts.at(c) + 1
          let nc1 = counts.at(c + 1) - 1
          let noff1 = offs.at(c + 1) + 1
          let h0-new = meas(nc0, offs.at(c), c == 0)
          let h1-new = meas(nc1, noff1, false)
          let t0-new = (if c == 0 { H0 } else { 0pt }) + h0-new + msg_sums.at(c)
          let t1-new = h1-new + msg_sums.at(c + 1)
          let nmx = t0-new
          if t1-new > nmx { nmx = t1-new }
          for q in range(n) {
            if q != c and q != c + 1 and totals.at(q) > nmx { nmx = totals.at(q) }
          }
          if nmx < cur-max and (best-c == -1 or nmx < cur-max - best-d) {
            best-d = cur-max - nmx
            best-c = c
            best-dir = 1
            best-h0 = h0-new
            best-h1 = h1-new
          }
        }
      }
    }
    if best-c == -1 { break }
    if best-dir == -1 {
      counts.at(best-c) = counts.at(best-c) - 1
      counts.at(best-c + 1) = counts.at(best-c + 1) + 1
    } else {
      counts.at(best-c) = counts.at(best-c) + 1
      counts.at(best-c + 1) = counts.at(best-c + 1) - 1
    }
    offs = offs-of(counts)
    ch.at(best-c) = best-h0
    ch.at(best-c + 1) = best-h1
    totals.at(best-c) = (if best-c == 0 { H0 } else { 0pt }) + best-h0 + msg_sums.at(best-c)
    totals.at(best-c + 1) = best-h1 + msg_sums.at(best-c + 1)
    cur-max = totals.fold(0pt, calc.max)
    last = -1
    for c in range(n) {
      if counts.at(c) > 0 { last = c }
    }
    if last < 1 { break }
  }
  let (cks, hs) = rebuild(counts)
  (counts, cks, hs)
}
#let render-balance-grid(n, titlepart, chunks, wrapped, col-idx) = {
  let cols = range(n).map(c => {
    let parts = ()
    if c == 0 and titlepart != none { parts.push(titlepart) }
    if chunks.at(c) != none { parts.push(chunks.at(c)) }
    for id in col-idx.at(c) { parts.push(wrapped.at(id)) }
    parts.join()
  })
  grid(columns: range(n).map(_ => 1fr), gutter: 4%, ..cols.map(c => [#c]))
}
#let decide-table(n, titlepart, rows, narrow, cw, H0, hs, tiers, list-title) = {
  let k = rows.len()
  let sum-hs = hs.fold(0pt, (a, b) => a + b)
  let mk-chunk = (cnt, off, first) => {
    if cnt == 0 { none } else {
      let t = due-table(rows.slice(off, off + cnt), narrow)
      if first and list-title != none { heading(level: 2)[#list-title] + t } else { t }
    }
  }
  if k <= n {
    let whole = if k == 0 {
      if list-title == none { due-table((), narrow) } else { heading(level: 2)[#list-title] + due-table((), narrow) }
    } else { mk-chunk(k, 0, true) }
    let loads = range(n).map(c => if c == 0 { H0 } else { 0pt })
    loads.at(0) = measure(block(width: cw, { set heading(numbering: stub-numbering); if titlepart == none { whole } else { titlepart + whole } })).height
    return ((k,) + range(n - 1).map(_ => 0), loads, (whole,) + range(n - 1).map(_ => none))
  }
  let T-whole = measure-chunk(cw, rows, narrow, list-title, k, 0, true)
  let trial = pack-tier0(n, tiers.at(0), hs, (H0 + T-whole,) + range(n - 1).map(_ => 0pt))
  trial = pack-lpt-rest(n, tiers.slice(1), hs, trial)
  let tH = trial.at(0)
  let W0 = tH.at(0)
  let Mothers = range(1, n).map(c => tH.at(c)).fold(0pt, calc.max)
  let fair = (H0 + T-whole + sum-hs) / n
  let target = calc.max(Mothers, fair)
  if W0 <= target {
    let whole = mk-chunk(k, 0, true)
    let loads = range(n).map(c => if c == 0 { H0 } else { 0pt })
    loads.at(0) = measure(block(width: cw, { set heading(numbering: stub-numbering); if titlepart == none { whole } else { titlepart + whole } })).height
    return ((k,) + range(n - 1).map(_ => 0), loads, (whole,) + range(n - 1).map(_ => none))
  }
  let m = 1
  while m < n and T-whole / m > target {
    m += 1
  }
  let counts = ()
  let chunks = ()
  let chunkhs = ()
  let pos = 0
  for c in range(n) {
    if c >= m {
      counts.push(0)
      chunks.push(none)
      chunkhs.push(0pt)
    } else if c == m - 1 {
      let cnt = k - pos
      chunks.push(mk-chunk(cnt, pos, false))
      chunkhs.push(measure-chunk(cw, rows, narrow, list-title, cnt, pos, false))
      counts.push(cnt)
      pos = k
    } else {
      let (cnt, h) = fit-rows(cw, rows, narrow, list-title, c == 0, pos, k, T-whole / m + T-whole / (2 * k), c == 0)
      if cnt == 0 {
        counts.push(0)
        chunks.push(none)
        chunkhs.push(0pt)
      } else {
        chunks.push(mk-chunk(cnt, pos, c == 0))
        chunkhs.push(h)
        counts.push(cnt)
        pos += cnt
      }
    }
  }
  let col-loads = range(n).map(c => (if c == 0 { H0 } else { 0pt }) + chunkhs.at(c))
  (counts, col-loads, chunks)
}
#let lec-balance(n, titlepart, rows, bodies, pris, narrow, list-title) = layout(size => {
  let gutter-abs = size.width * 0.04
  let cw = (size.width - (n - 1) * gutter-abs) / n
  let H0 = if titlepart == none { 0pt } else { measure(block(width: cw, { set heading(numbering: stub-numbering); titlepart })).height }
  let hs = measure-bodies(cw, bodies)
  let wrapped = wrap-bodies(bodies, hs)
  let tiers = pack-tiers(n, hs, pris)
  let (fcounts, fchunks, st) = if rows.len() == 0 {
    let loads0 = range(n).map(c => if c == 0 { H0 } else { 0pt })
    let all-open = range(n).map(_ => true)
    let st0 = pack-tier0(n, tiers.at(0), hs, loads0, allowed: all-open)
    st0 = pack-lpt-rest(n, tiers.slice(1), hs, st0, allowed: all-open)
    st0 = enforce-min-blank(n, st0, hs, pris)
    (range(n).map(_ => 0), range(n).map(_ => none), st0)
  } else {
    let (tcounts, col-loads, chunks) = decide-table(n, titlepart, rows, narrow, cw, H0, hs, tiers, list-title)
    let allowed = table-allowed(n, tcounts)
    let st1 = pack-tier0(n, tiers.at(0), hs, col-loads, allowed: allowed)
    st1 = pack-lpt-rest(n, tiers.slice(1), hs, st1, allowed: allowed)
    let (_pcounts, pchunks, _pcolh, pchunkhs) = left-pack-table(n, rows, narrow, cw, list-title, tcounts, chunks, st1.at(0))
    let fresh-loads = range(n).map(c => (if c == 0 { H0 } else { 0pt }) + pchunkhs.at(c))
    let allowed2 = table-allowed(n, _pcounts)
    st1 = pack-tier0(n, tiers.at(0), hs, fresh-loads, allowed: allowed2)
    st1 = pack-lpt-rest(n, tiers.slice(1), hs, st1, allowed: allowed2)
    let msg-sums = range(n).map(c => st1.at(0).at(c) - fresh-loads.at(c))
    let ntab = _pcounts.filter(v => v > 0).len()
    let (fcounts2, fchunks2, fchunkhs) = if ntab < 2 {
      (_pcounts, pchunks, pchunkhs)
    } else {
      balance-table-cols(n, rows, narrow, cw, list-title, H0, _pcounts, msg-sums)
    }
    if fchunks2.at(0) == none and _pcounts.at(0) > 0 {
      fcounts2 = _pcounts
      fchunks2 = pchunks
      fchunkhs = pchunkhs
    }
    let fresh2 = range(n).map(c => (if c == 0 { H0 } else { 0pt }) + fchunkhs.at(c))
    let allowed3 = table-allowed(n, fcounts2)
    st1 = pack-tier0(n, tiers.at(0), hs, fresh2, allowed: allowed3)
    st1 = pack-lpt-rest(n, tiers.slice(1), hs, st1, allowed: allowed3)
    st1 = enforce-min-blank(n, st1, hs, pris)
    (fcounts2, fchunks2, st1)
  }
  let _dbg = if sys.inputs.at("dbg", default: "0") == "1" {
    [#v(4pt)#text(size: 6pt, fill: red)[DBG list=#list-title counts=#fcounts loads=#st.at(0).map(h => str(calc.round(h / 1pt))) idx=#st.at(1) Blank]]
  } else { [] }
  [#render-balance-grid(n, titlepart, fchunks, wrapped, st.at(1))#_dbg]
})

#let wrap(lnk, body) = wrap-it.wrap-content(
tiaoma.qrcode(lnk),
body+[#v(1em, weak: true)
  详见：#link(lnk)],
align: bottom+right,
column-gutter: 1em
)

#show "习近平": "⍰⍰⍰"

#show link: it =>{underline(stroke: (dash: "densely-dotted", paint: rgb(222, 130, 167, 255), thickness: 1pt), text(font: ("DejaVu Sans Mono", "Noto Sans CJK SC"), fill:rgb("#2a0029"), it))}

#set text(font: ("New Computer Modern", "Noto Sans CJK SC"), size: 12pt)
#set par(first-line-indent: 0pt, leading: 0.8em)

#set heading(numbering: "1.1.1.")

#show heading: it =>{
  set text(font: ("New Computer Modern", "Noto Serif CJK SC"), fill: rgb(51, 0, 26, 255))
  it
}

#let msg-block(e, level: 2, imgnote: true, raw: false) = {
  let inner = [
  #heading(level: level)[#e.at("title")]
  #if (e.at("link", default: none) == none) or (("", "none", "None").contains(e.at("link", default: none))) {
    for sub in e.at("description") {
    if sub.at("type") == "text" and (sub.at("content") not in ("None",)) {sub.at("content")}
    if sub.at("type") == "link" {link(sub.at("content"))}
  }
  } else {
    box(wrap(e.at("link"))[#for sub in e.at("description") {
    if sub.at("type") == "text" and (sub.at("content") not in ("None",)) {sub.at("content")}
    if sub.at("type") == "link" {link(sub.at("content"))}
  }] )
  }
  #let im = e.at("image", default: none)
  #if im != none and imgnote [
    #v(1em, weak: true)
    图片见PDF文档第二页#ref(label("fig-img-" + str(e.at("id"))))
  ]
  #if im != none and not imgnote {
    image("static/uploads/" + im, width: 100%)
  }
  ]
  if raw { inner } else { block(breakable: false, width: 100%, inner) }
}

#let lec-section(msgs, rows, level: 1, narrow-first-col: false) = {
  if msgs.len() == 0 and rows.len() == 0 { [] } else {
    let bodies = msgs.map(e => msg-block(e, level: level, raw: true))
    let pris = msgs.map(e => int(e.at("priority", default: 0)))
    [#lec-balance(ncols, none, rows, bodies, pris, narrow-first-col, none)
     #line(length: 100%)]
  }
}

#if lecture.len() > 0 [
  #align(center)[
    #text(size: 2.5em, weight: "bold", font: ("Noto Serif CJK SC"))[#v(-0.5em)讲座预告#v(-0.5em)]
  ]
  #lec-section(lecture, (), level: 1)
]

#let past-rows = lecture-due.filter(e => e.at("due_time") != none)
#if past-rows.len() > 0 [
  #align(center)[
    #text(size: 2.5em, weight: "bold", font: ("Noto Serif CJK SC"))[#v(-0.5em)往期讲座#v(-0.5em)]
  ]
  #lec-section((), past-rows, narrow-first-col: true)
]

#let img-msgs = lecture.filter(e => e.at("image", default: none) != none)
#if img-msgs.len() > 0 {
  pagebreak()
  align(center)[
    #text(size: 3em, weight: "bold", font: ("Noto Serif CJK SC"))[图片附页]
  ]
  v(-4mm)
  show figure.caption: set text(size: 0.8em)
  grid(
    columns: (1fr, 1fr, 1fr, 1fr),
    gutter: 1em,
    ..img-msgs.map(e => [
      #figure(image("static/uploads/" + e.at("image"), width: 100%), caption: [#e.at("title")], supplement: [图])
      #label("fig-img-" + str(e.at("id")))
    ])
  )
}
