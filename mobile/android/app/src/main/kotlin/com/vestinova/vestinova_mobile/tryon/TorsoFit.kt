package com.vestinova.vestinova_mobile.tryon

import kotlin.math.*

/** Half widths, in shoulder-span units, at 0, 25, 50, 75 and 100% of the torso. */
internal data class TorsoOutline(val widths:List<Point2>) {
    fun usable()=widths.size==5 && widths.all { it.x.isFinite() && it.y.isFinite() && it.x in .25f.. .7f && it.y in .25f.. .7f }
    fun at(fraction:Float):Point2 {
        val index=(fraction.coerceIn(0f,1f)*4).coerceAtMost(3.9999f)
        val lower=index.toInt();val t=index-lower
        return widths[lower]*(1-t)+widths[lower+1]*t
    }
}

/** Foreground probabilities belong to the same oriented frame as the pose.
 * This estimates a bounded torso outline, not clothing segmentation or body size.
 * Reject rows connected to arms/background beyond the permitted search window.
 */
internal fun torsoOutline(body:BodyPoints,probability:(Point2)->Float):TorsoOutline? {
    if(!body.usable())return null
    val p=body.points
    val span=(p[1]-p[0]).length();val across=(p[1]-p[0])*(1/span)
    val top=(p[0]+p[1])*.5f;val bottom=(p[2]+p[3])*.5f
    val measured=MutableList<Point2?>(5) { null };measured[0]=Point2(.5f,.5f)
    fun extent(center:Point2,sign:Float):Float? {
        var missing=0
        for(step in 1..67) {
            val confidence=probability(center+across*(span*.01f*step*sign))
            if(!confidence.isFinite())return null
            missing=if(confidence<.65f)missing+1 else 0
            if(missing>=3) {
                val distance=(step-2)*.01f
                return distance.takeIf { it in .28f.. .65f }
            }
        }
        return null // merged arm or unbounded foreground: do not treat it as torso.
    }
    for(index in 1..4) {
        val t=index/4f;val center=top*(1-t)+bottom*t
        if(probability(center).let { !it.isFinite() || it<.8f })continue
        val left=extent(center,-1f);val right=extent(center,1f)
        if(left!=null && right!=null && left+right in .6f..1.25f)measured[index]=Point2(left,right)
    }
    if(measured.drop(1).count { it!=null }<3)return null
    for(index in 1..4)if(measured[index]==null) {
        val lower=(index-1 downTo 0).first { measured[it]!=null }
        val upper=(index+1..4).firstOrNull { measured[it]!=null }
        measured[index]=if(upper==null)measured[lower] else {
            val t=(index-lower).toFloat()/(upper-lower)
            measured[lower]!!*(1-t)+measured[upper]!!*t
        }
    }
    return TorsoOutline(measured.map { requireNotNull(it) }).takeIf { it.usable() }
}
