package com.vestinova.vestinova_mobile.tryon

import kotlin.math.*

internal data class GarmentPlacement(val x:Float,val y:Float,val width:Float,val height:Float,val angle:Float)

/** Fits inside the calibrated box with ONE scale; a PNG must never stretch in X/Y independently. */
internal fun projectTorso(a:FloatArray,w:Int,h:Int,config:List<Float>,garmentAspect:Float=.8f):GarmentPlacement? {
    if(a.size!=7 || w<=0 || h<=0 || config.size!=4 || a.any { !it.isFinite() || it !in 0f..1f }
        || config.any { !it.isFinite() } || !garmentAspect.isFinite() || garmentAspect<=0)return null
    val shoulder=hypot((a[3]-a[5])*w,(a[4]-a[6])*h)
    val torso=(a[2]-a[1])*h
    // Reject collapsed/side-on shoulders and a torso that is too small or incomplete.
    if(shoulder<min(w,h)*.12f || torso<h*.12f || shoulder/torso !in .35f..1.8f
        || config[0]<=0 || config[1]<=0)return null
    var angle=atan2((a[6]-a[4])*h,(a[5]-a[3])*w)*180/PI.toFloat()
    if(angle>90)angle-=180;if(angle< -90)angle+=180
    if(abs(angle)>35f)return null
    val height=min(torso*config[1],shoulder*config[0]/garmentAspect)
    return GarmentPlacement(a[0]*w+shoulder*config[2],(a[1]+a[2])/2*h+torso*config[3],height*garmentAspect,height,angle)
}

/** Three stable frames to acquire/reacquire; invalid frames hide the image immediately. */
internal class PlacementSmoother {
    private var current:GarmentPlacement?=null
    private var candidate:GarmentPlacement?=null
    private var count=0
    private var lastTime=0L

    fun reset() { current=null;candidate=null;count=0;lastTime=0 }

    fun update(target:GarmentPlacement?,time:Long):GarmentPlacement? {
        if(target==null) { reset();return null }
        if(lastTime>0 && (time<=lastTime || time-lastTime>500))reset()
        val previous=current
        val elapsed=if(lastTime>0)time-lastTime else 70L
        lastTime=time
        if(previous!=null && nearby(previous,target)) {
            val alpha=(1f-exp(-elapsed/120f)).coerceIn(.15f,.65f)
            fun blend(a:Float,b:Float)=a+(b-a)*alpha
            current=GarmentPlacement(blend(previous.x,target.x),blend(previous.y,target.y),
                blend(previous.width,target.width),blend(previous.height,target.height),blend(previous.angle,target.angle))
            return current
        }
        current=null
        count=if(candidate?.let { nearby(it,target) }==true)count+1 else 1
        candidate=target
        if(count>=3) { current=target;candidate=null;count=0 }
        return current
    }

    private fun nearby(a:GarmentPlacement,b:GarmentPlacement):Boolean =
        b.width/a.width in .75f..1.33f && b.height/a.height in .75f..1.33f &&
            hypot(b.x-a.x,b.y-a.y)<a.height*.35f && abs(b.angle-a.angle)<20f
}
