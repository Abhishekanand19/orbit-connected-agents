import React from 'react';
export default function Avatar({shape=0, color='#ed947e', size=44, className=''}) {
 const shapes = [
  <path d="M20 23Q22 12 36 15Q51 9 57 23Q70 25 64 40Q72 55 57 59Q49 71 36 62Q20 70 17 56Q4 48 14 36Q8 25 20 23Z"/>,
  <path d="M18 24Q18 15 28 15H49Q59 15 59 25V57Q59 64 50 64H26Q17 64 17 55Z"/>,
  <path d="M11 45Q9 33 21 29Q19 14 33 17Q43 5 52 21Q68 20 65 35Q78 47 62 55Q63 68 49 62Q36 74 29 60Q13 64 15 52Z"/>,
  <path d="M13 38Q13 15 38 15Q64 15 64 38Q64 59 44 60L26 69V59Q13 54 13 38Z"/>,
  <path d="M24 14Q38 8 51 17L66 40Q71 52 59 59L34 66Q22 68 17 56L10 35Q8 25 24 14Z"/>
 ];
 return <svg className={`avatar ${className}`} style={{'--avatar-offset':`${shape*1.1}s`}} width={size} height={size} viewBox="0 0 78 78" fill="none" aria-hidden="true"><g fill={color}>{shapes[shape]}</g>{shape===1&&<path d="M25 14V10M50 14V10" stroke={color} strokeWidth="5" strokeLinecap="round"/>}<g className="face" fill="#29272c"><ellipse cx="29" cy="37" rx="3" ry={shape===2?4:5}/><ellipse cx="47" cy="37" rx="3" ry="5"/></g><path d={shape===4?'M34 49L38 51L43 47':'M34 48Q38 52 43 48'} stroke="#29272c" strokeWidth="2.3" strokeLinecap="round"/>{shape===2&&<g stroke="#314437" strokeWidth="2"><circle cx="28" cy="37" r="8"/><circle cx="48" cy="37" r="8"/><path d="M36 37H40"/></g>}{shape===3&&<path d="M54 25L57 22" stroke="#fff6df" strokeWidth="3" strokeLinecap="round"/>}</svg>;
}
