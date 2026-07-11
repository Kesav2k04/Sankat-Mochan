import { useEffect, useRef } from 'react'
import lottie from 'lottie-web'

export default function Lottie({ data, className }) {
  const ref = useRef(null)
  useEffect(() => {
    const anim = lottie.loadAnimation({ container: ref.current, renderer: 'svg', loop: true, autoplay: true, animationData: data })
    return () => anim.destroy()
  }, [data])
  return <div ref={ref} className={className} />
}
