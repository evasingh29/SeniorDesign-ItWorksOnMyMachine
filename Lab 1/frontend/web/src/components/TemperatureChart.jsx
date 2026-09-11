import { useEffect, useRef } from 'react'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import {
  HISTORY_SECONDS,
  SENSOR_COLORS,
  SENSOR_KEYS,
  SENSOR_LABELS,
  Y_MAX_C,
  Y_MIN_C,
} from '../lib/constants.js'
import { UNIT_F, cToF, formatTemp, unitSymbol } from '../lib/temperature.js'

/**
 * The x axis is "seconds ago": a fixed 0..300 domain that never moves. Samples
 * are placed by age, not by timestamp, so appending a sample shifts every
 * existing point one step left — the chart-recorder scroll — without us ever
 * touching the scale.
 *
 * Drawn reversed (300 on the left, 0 on the right) via uPlot's scale `dir`.
 */
/**
 * x values are "seconds ago", stored ASCENDING (0 = newest, 299 = oldest).
 *
 * Ascending order is required: uPlot binary-searches this array to resolve the
 * cursor to an index, and that search assumes ascending x. A descending array
 * makes the search collapse to the endpoints, so the hover readout snaps
 * between the two extremes instead of tracking the pointer.
 *
 * The visual reversal (300 on the left, 0 on the right) is done by the scale's
 * `dir: -1`, not by the data order.
 */
const X_AGES = Array.from({ length: HISTORY_SECONDS }, (_, i) => i)

/**
 * Shades the spans where a trace has no data.
 *
 * This is the requirement that missing data must not be confusable with
 * off-scale data. A break in the line alone is ambiguous at a glance — it can
 * read as a flat segment or a rendering artifact — so every null run gets a
 * hatched band, tinted in that sensor's pen color so you can tell *which*
 * sensor is missing. Off-scale data still draws as a line clipped at the axis
 * bound, which looks nothing like hatching.
 *
 * Shading is per-sensor, not "all sensors missing": in practice the sensors
 * fail independently, so a shared-gap-only rule would leave the common case
 * (one sensor unplugged, the other fine) completely unmarked.
 */
function gapShadingPlugin() {
  const hatches = new Map()

  const hatchFor = (ctx, color) => {
    if (hatches.has(color)) return hatches.get(color)
    const tile = document.createElement('canvas')
    tile.width = 8
    tile.height = 8
    const tctx = tile.getContext('2d')
    tctx.strokeStyle = color
    tctx.globalAlpha = 0.55
    tctx.lineWidth = 1.5
    tctx.beginPath()
    tctx.moveTo(-2, 10)
    tctx.lineTo(10, -2)
    tctx.moveTo(-2, 18)
    tctx.lineTo(18, -2)
    tctx.stroke()
    const pattern = ctx.createPattern(tile, 'repeat')
    hatches.set(color, pattern)
    return pattern
  }

  return {
    hooks: {
      // draw fires before the series are stroked, so hatching sits behind the pens.
      draw: (u) => {
        const ctx = u.ctx
        const { left, top, width, height } = u.bbox

        ctx.save()
        ctx.beginPath()
        ctx.rect(left, top, width, height)
        ctx.clip()

        const xs = u.data[0]

        SENSOR_KEYS.forEach((key, s) => {
          const values = u.data[s + 1]
          // Full-height bands, so a gap is unmissable at a glance. The hatch
          // is tinted in the sensor's pen color to say which trace is out;
          // overlapping gaps cross-hatch, which still reads as "no data".
          const bandTop = top
          const bandHeight = height
          const pattern = hatchFor(ctx, SENSOR_COLORS[key])

          let runStart = null
          for (let i = 0; i <= values.length; i += 1) {
            const missing = i < values.length && values[i] === null

            if (missing && runStart === null) runStart = i

            if (!missing && runStart !== null) {
              const endIdx = i - 1
              // Extend half a sample each way so a lone missing point is visible.
              const x0 = u.valToPos(xs[runStart] - 0.5, 'x', true)
              const x1 = u.valToPos(xs[endIdx] + 0.5, 'x', true)
              const bandLeft = Math.min(x0, x1)
              const bandWidth = Math.max(Math.abs(x1 - x0), 2)

              ctx.fillStyle = pattern
              ctx.fillRect(bandLeft, bandTop, bandWidth, bandHeight)
              runStart = null
            }
          }
        })

        ctx.restore()
      },
    },
  }
}

export default function TemperatureChart({ buffer, tick, unit, onHover }) {
  const containerRef = useRef(null)
  const plotRef = useRef(null)
  const unitRef = useRef(unit)
  const onHoverRef = useRef(onHover)
  const tipRef = useRef(null)
  const tipAgeRef = useRef(null)
  const tipRowsRef = useRef(null)

  // Kept in a ref so the axis formatter reads the current unit without the
  // plot needing to be rebuilt.
  unitRef.current = unit
  onHoverRef.current = onHover

  // Built exactly once. `data` is deliberately absent from the dependency
  // array — including it would tear down and recreate the canvas every second.
  useEffect(() => {
    const series = [
      {},
      ...SENSOR_KEYS.map((key) => ({
        label: SENSOR_LABELS[key],
        stroke: SENSOR_COLORS[key],
        width: 1.75,
        // Do not bridge nulls: a gap must stay a gap.
        spanGaps: false,
        points: { show: false },
      })),
    ]

    const opts = {
      // Without this, uPlot treats x values as Unix timestamps and prints 1970.
      // Our x values are ages in seconds, so plain numbers are what we want.
      scales: {
        x: { time: false, range: [0, HISTORY_SECONDS - 1], dir: -1 },
        // Hard bounds. A range function that ignores its arguments is the only
        // way to guarantee uPlot never auto-scales, whatever the data does.
        y: { range: () => [Y_MIN_C, Y_MAX_C] },
      },
      axes: [
        {
          label: 'seconds ago',
          labelSize: 26,
          labelFont: '600 11px ui-sans-serif, system-ui, sans-serif',
          font: '11px ui-monospace, SFMono-Regular, Menlo, monospace',
          stroke: '#4a443d',
          grid: { stroke: 'rgba(96, 88, 78, 0.16)', width: 1 },
          ticks: { stroke: 'rgba(96, 88, 78, 0.45)', width: 1, size: 5 },
          splits: () => [300, 240, 180, 120, 60, 0],
          values: (_u, splits) => splits.map((v) => String(v)),
        },
        {
          // Ticks are generated in Celsius (the scale's real unit) and only the
          // printed label is converted, so the axis never lies about position.
          label: () => `temperature (${unitSymbol(unitRef.current)})`,
          labelSize: 30,
          labelFont: '600 11px ui-sans-serif, system-ui, sans-serif',
          font: '11px ui-monospace, SFMono-Regular, Menlo, monospace',
          stroke: '#4a443d',
          grid: { stroke: 'rgba(96, 88, 78, 0.16)', width: 1 },
          ticks: { stroke: 'rgba(96, 88, 78, 0.45)', width: 1, size: 5 },
          splits: () => [10, 15, 20, 25, 30, 35, 40, 45, 50],
          values: (_u, splits) =>
            splits.map((c) =>
              unitRef.current === UNIT_F ? String(Math.round(cToF(c))) : String(c),
            ),
        },
      ],
      series,
      legend: { show: false },
      cursor: {
        // A vertical rule only: no dot markers, no drag-zoom (the window is
        // fixed at 300 s), and crucially no re-render of this component.
        x: true,
        y: false,
        drag: { x: false, y: false, setScale: false },
        points: { show: false },
        // setCursor fires on every mouse move; it reports upward through a
        // ref, so the React tree above can render a readout without this
        // effect ever re-running and rebuilding the canvas.
        bind: {
          mouseleave: (u, targ, handler) => (e) => {
            handler(e)
            if (onHoverRef.current) onHoverRef.current(null)
            return null
          },
        },
      },
      // Tight outer padding: the paper area is small, so default padding
      // wastes a visible fraction of it.
      padding: [10, 10, 2, 4],
      plugins: [gapShadingPlugin()],
      hooks: {
        setCursor: [
          (u) => {
            const idx = u.cursor.idx
            const tip = tipRef.current
            const cb = onHoverRef.current

            if (idx === null || idx === undefined) {
              if (tip) tip.hidden = true
              if (cb) cb(null)
              return
            }

            const secondsAgo = u.data[0][idx]
            const values = SENSOR_KEYS.map((key, s) => ({ key, c: u.data[s + 1][idx] }))

            if (cb) cb({ secondsAgo, values, left: u.cursor.left })

            // Tooltip: written straight to the DOM. Doing this through React
            // state would re-render on every mouse move, and the chart's build
            // effect must stay untouched.
            if (!tip) return
            const unitLabel = unitSymbol(unitRef.current)

            tipAgeRef.current.textContent = `t \u2212 ${secondsAgo}s`
            tipRowsRef.current.innerHTML = values
              .map(({ key, c }) => {
                const reading =
                  c === null || c === undefined
                    ? 'no data'
                    : `${formatTemp(c, unitRef.current)}${unitLabel}`
                return (
                  `<div class="tip__row">` +
                  `<span class="tip__dot" style="background:${SENSOR_COLORS[key]}"></span>` +
                  `<span class="tip__name">${SENSOR_LABELS[key]}</span>` +
                  `<span class="tip__val">${reading}</span>` +
                  `</div>`
                )
              })
              .join('')

            tip.hidden = false

            // Flip to the left of the cursor near the right edge so the
            // tooltip never runs outside the plot area.
            const pad = 14
            const tipW = tip.offsetWidth
            const plotRight = u.bbox.left / devicePixelRatio + u.bbox.width / devicePixelRatio
            let x = u.cursor.left + pad
            if (x + tipW > plotRight) x = u.cursor.left - tipW - pad

            tip.style.transform = `translate(${Math.round(x)}px, ${Math.round(u.cursor.top + pad)}px)`
          },
        ],
      },
      width: containerRef.current.clientWidth,
      height: containerRef.current.clientHeight,
    }

    const emptyRow = new Array(HISTORY_SECONDS).fill(null)
    const plot = new uPlot(
      opts,
      [X_AGES, ...SENSOR_KEYS.map(() => emptyRow.slice())],
      containerRef.current,
    )
    plotRef.current = plot

    const resize = () => {
      plot.setSize({
        width: containerRef.current.clientWidth,
        height: containerRef.current.clientHeight,
      })
    }
    const observer = new ResizeObserver(resize)
    observer.observe(containerRef.current)

    return () => {
      observer.disconnect()
      plot.destroy()
      plotRef.current = null
    }
  }, [])

  // Push new data into the existing instance. No teardown, no re-creation.
  useEffect(() => {
    const plot = plotRef.current
    if (!plot) return

    // The buffer runs oldest -> newest; x runs newest (age 0) -> oldest
    // (age 299), so the mapping reverses. A partially filled buffer (the live
    // feed on startup) leaves the high-age end empty, which renders as blank
    // space on the left rather than stretching the history it does have.
    const size = buffer.size

    const rows = SENSOR_KEYS.map((key) => {
      const values = buffer.valuesFor(key)
      const row = new Array(HISTORY_SECONDS).fill(null)
      for (let age = 0; age < size; age += 1) {
        row[age] = values[size - 1 - age]
      }
      return row
    })

    plot.setData([X_AGES, ...rows])
  }, [tick, buffer])

  // Unit changes only affect axis labels, so redraw without rebuilding.
  useEffect(() => {
    if (plotRef.current) plotRef.current.redraw(false, true)
  }, [unit])

  return (
    <div className="chart-wrap">
      <div className="chart-canvas" ref={containerRef} />
      {/* Tooltip is written imperatively from the cursor hook below, so
          following the pointer never re-renders this component. */}
      <div className="tip" ref={tipRef} hidden>
        <div className="tip__age" ref={tipAgeRef} />
        <div className="tip__rows" ref={tipRowsRef} />
      </div>
    </div>
  )
}
