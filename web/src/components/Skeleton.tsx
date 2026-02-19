interface SkeletonProps {
  width?: string | number
  height?: string | number
  className?: string
  style?: React.CSSProperties
}

export function Skeleton({ width, height, className = '', style }: SkeletonProps) {
  return (
    <div
      className={`skeleton ${className}`}
      style={{
        width: width ?? '100%',
        height: height ?? '1em',
        ...style,
      }}
    />
  )
}

export function SkeletonTable({ rows = 10 }: { rows?: number }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th style={{ width: 32 }}></th>
            <th><Skeleton width={120} height={14} /></th>
            <th><Skeleton width={100} height={14} /></th>
            <th><Skeleton width={150} height={14} /></th>
            <th><Skeleton width={70} height={14} /></th>
            <th><Skeleton width={40} height={14} /></th>
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: rows }).map((_, i) => (
            <tr key={i}>
              <td><Skeleton width={16} height={16} /></td>
              <td><Skeleton width="80%" height={16} /></td>
              <td><Skeleton width="60%" height={16} /></td>
              <td><Skeleton width="70%" height={16} /></td>
              <td><Skeleton width={60} height={16} /></td>
              <td><Skeleton width={30} height={16} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function SkeletonStatCards() {
  return (
    <div className="card-grid" style={{ marginBottom: '2rem' }}>
      {[1, 2, 3].map((i) => (
        <div key={i} className="stat-card">
          <Skeleton width={60} height={28} style={{ marginBottom: '0.5rem' }} />
          <Skeleton width={100} height={14} />
        </div>
      ))}
    </div>
  )
}

export function SkeletonList({ items = 5 }: { items?: number }) {
  return (
    <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
      {Array.from({ length: items }).map((_, i) => (
        <li key={i} style={{ padding: '0.5rem 0', borderBottom: '1px solid var(--border)', display: 'flex', gap: '0.5rem', alignItems: 'baseline' }}>
          <Skeleton width={18} height={14} />
          <Skeleton width={`${60 + i * 5}%`} height={16} />
          <Skeleton width={80} height={14} style={{ marginLeft: 'auto' }} />
        </li>
      ))}
    </ul>
  )
}

export default Skeleton
