import Skeleton from './Skeleton'

interface PageSkeletonProps {
  /** Optional title bar width (default 320) */
  titleWidth?: number
  /** Number of content blocks (default 2) */
  blocks?: number
}

/**
 * Consistent loading layout for detail pages: title bar + content blocks.
 */
export function PageSkeleton({ titleWidth = 320, blocks = 2 }: PageSkeletonProps) {
  return (
    <div className="page">
      <Skeleton width={titleWidth} height={32} />
      <Skeleton width={120} height={20} style={{ marginTop: '0.5rem' }} />
      {Array.from({ length: blocks }).map((_, i) => (
        <Skeleton key={i} width="100%" height={200} style={{ marginTop: '1.5rem' }} />
      ))}
    </div>
  )
}

export default PageSkeleton
