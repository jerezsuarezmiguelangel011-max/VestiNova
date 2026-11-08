package com.vestinova.vestinova_mobile.tryon

import kotlin.math.*

internal data class Point2(val x:Float,val y:Float) {
    operator fun plus(other:Point2)=Point2(x+other.x,y+other.y)
    operator fun minus(other:Point2)=Point2(x-other.x,y-other.y)
    operator fun times(value:Float)=Point2(x*value,y*value)
    fun length()=hypot(x,y)
    fun dot(other:Point2)=x*other.x+y*other.y
    fun perpendicular()=Point2(-y,x)
}

internal val ANCHOR_KEYS=listOf("hombro_izq","hombro_der","cintura_izq","cintura_der",
    "manga_izq_media","manga_izq_fin","manga_der_media","manga_der_fin")

internal data class ImageAnchors(val points:List<Point2>,val longSleeves:Boolean) {
    companion object {
        fun from(value:Map<*,*>):ImageAnchors {
            val points=ANCHOR_KEYS.map { key ->
                val point=value[key] as Map<*,*>
                Point2((point["x"] as Number).toFloat(),(point["y"] as Number).toFloat())
            }
            require(points.all { it.x.isFinite() && it.y.isFinite() && it.x in 0f..1f && it.y in 0f..1f })
            require(points[1].x-points[0].x>=.15f && points[3].x-points[2].x>=.1f)
            require(min(points[2].y,points[3].y)-max(points[0].y,points[1].y)>=.2f)
            require(value["manga"]=="LARGA" || value["manga"]=="CORTA")
            for((root,middle,end) in listOf(Triple(0,4,5),Triple(1,6,7))) {
                require((points[middle]-points[root]).length()>=.05f && (points[end]-points[middle]).length()>=.05f)
            }
            require(listOf(4,5).all { points[it].x<=points[0].x+.04f } && listOf(6,7).all { points[it].x>=points[1].x-.04f })
            return ImageAnchors(points,value["manga"]=="LARGA")
        }
    }
}

/** Screen-left/right, after the same rotation and mirroring as the camera frame. */
internal data class BodyPoints(val points:List<Point2>,val outline:TorsoOutline?=null) {
    fun usable():Boolean {
        if(points.size!=8 || points.any { !it.x.isFinite() || !it.y.isFinite() })return false
        val span=(points[1]-points[0]).length()
        val torso=((points[2]+points[3])*.5f-(points[0]+points[1])*.5f).length()
        return span>30f && torso>50f && span/torso in .35f..1.8f && points[1].x>points[0].x &&
            points[3].x>points[2].x && min(points[2].y,points[3].y)>max(points[0].y,points[1].y)+span*.4f &&
            abs(atan2(points[1].y-points[0].y,points[1].x-points[0].x))<.6f &&
            listOf(0 to 4,4 to 5,1 to 6,6 to 7).all { (a,b) -> (points[b]-points[a]).length()>span*.1f }
    }
}

internal class BodySmoother {
    private var previous:BodyPoints?=null
    private var candidate:BodyPoints?=null
    private var count=0
    private var last=0L
    fun reset() { previous=null;candidate=null;count=0;last=0 }
    fun update(next:BodyPoints?,time:Long):BodyPoints? {
        if(next==null || !next.usable()) { reset();return null }
        if(last>0 && (time<=last || time-last>500))reset()
        val alpha=(1f-exp(-(if(last>0)time-last else 70L)/100f)).coerceIn(.2f,.7f)
        last=time
        fun near(a:BodyPoints,b:BodyPoints):Boolean {
            val span=(a.points[1]-a.points[0]).length()
            val ratio=(b.points[1]-b.points[0]).length()/span
            return ratio in .75f..1.33f && a.points.zip(b.points).all { (p,q) -> (p-q).length()<span*.8f }
        }
        previous?.let { old ->
            if(near(old,next)) {
                val outline=next.outline?.takeIf { it.usable() }?.let { fresh ->
                    val before=old.outline?.takeIf { it.usable() } ?: TorsoOutline(List(5) { Point2(.5f,.5f) })
                    TorsoOutline(before.widths.zip(fresh.widths).map { (a,b) -> a*(1-alpha)+b*alpha })
                }
                previous=BodyPoints(old.points.zip(next.points).map { (a,b) -> a*(1-alpha)+b*alpha },outline)
                return previous
            }
        }
        previous=null
        count=if(candidate?.let { near(it,next) }==true)count+1 else 1
        candidate=next
        if(count>=3) { previous=next;candidate=null;count=0 }
        return previous
    }
}

/** Piecewise 2D skinning: calibrated torso + shoulder/elbow/wrist sleeve chains. */
internal class GarmentMesh(anchors:ImageAnchors,val body:BodyPoints,val imageWidth:Int,val imageHeight:Int) {
    private val source=anchors.points.map { Point2(it.x*imageWidth,it.y*imageHeight) }
    private var target=fitTorso(body)
    private var thickness=if(body.usable())(target[1]-target[0]).length()/(source[1]-source[0]).length() else 0f
    // Source inversion is constant for a photo; do it once, not on every camera frame.
    private val sourceCoordinates=HashMap<Point2,Point2>()
    private var outline=body.outline?.takeIf { it.usable() }

    private fun fitTorso(body:BodyPoints):List<Point2> {
        if(!body.usable())return body.points
        val points=body.points
        val shoulders=(points[1]-points[0]).length()
        val hips=points[3]-points[2]
        // Hip landmarks are internal joints, not the outline of a shirt. Preserve
        // at least the photo's hem/shoulder proportion instead of cinching it.
        val sourceRatio=(source[3]-source[2]).length()/(source[1]-source[0]).length()
        val width=max(hips.length(),shoulders*sourceRatio)
        val center=(points[2]+points[3])*.5f
        val half=hips*(width/(2*hips.length()))
        return points.toMutableList().apply { this[2]=center-half;this[3]=center+half }
    }

    private fun bilinear(points:List<Point2>,u:Float,v:Float):Point2 =
        points[0]*((1-u)*(1-v))+points[1]*(u*(1-v))+points[2]*((1-u)*v)+points[3]*(u*v)

    private fun torsoPoint(u:Float,v:Float):Point2 {
        val span=(target[1]-target[0]).length()
        if(v<0) {
            // Restore the pre-0.1.4 upper projection. Compressing this area
            // independently flattened the collar and shoulder contour in practice.
            return bilinear(target,u,v)
        }
        val across=(target[1]-target[0])*(1/span)
        val left=target[0]*(1-v)+target[2]*v;val right=target[1]*(1-v)+target[3]*v
        val center=(left+right)*.5f
        val t=(v/.3f).coerceIn(0f,1f);val influence=t*t*(3-2*t)
        val measured=outline?.at(v)
        fun extra(half:Float,known:Float?):Float {
            // Small garment ease even without a reliable mask; mask expansion is
            // bounded and never narrows the preserved cut or expands shoulder roots.
            val requested=max(half*1.045f,known?.let { (it+.025f)*span } ?: half)
            return (requested-half).coerceIn(0f,span*.12f)*influence
        }
        val fittedLeft=left-across*extra((center-left).length(),measured?.x)
        val fittedRight=right+across*extra((right-center).length(),measured?.y)
        return fittedLeft*(1-u)+fittedRight*u
    }

    private fun torsoCoordinates(point:Point2):Point2 {
        var u=.5f;var v=.5f
        // Invert the calibrated quad rather than assuming the complete PNG is a torso.
        repeat(8) {
            val current=bilinear(source,u,v)
            val du=(source[1]-source[0])*(1-v)+(source[3]-source[2])*v
            val dv=(source[2]-source[0])*(1-u)+(source[3]-source[1])*u
            val determinant=du.x*dv.y-du.y*dv.x
            if(abs(determinant)<.001f)return Point2(Float.NaN,Float.NaN)
            val delta=point-current
            u+=(delta.x*dv.y-delta.y*dv.x)/determinant
            v+=(du.x*delta.y-du.y*delta.x)/determinant
        }
        return Point2(u,v)
    }

    private data class BoneProjection(val result:Point2,val distance:Float,val along:Float)
    private fun bone(point:Point2,a:Int,b:Int,alongOffset:Float):BoneProjection {
        val start=source[a];val direction=source[b]-start;val length=direction.length()
        if(length<1f)return BoneProjection(target[a],Float.MAX_VALUE,0f)
        val unit=direction*(1/length)
        val ratio=(point-start).dot(unit)/length
        val distance=(point-(start+direction*ratio.coerceIn(0f,1f))).length()
        val destination=target[b]-target[a];val targetUnit=destination*(1/destination.length())
        val across=(point-start).dot(unit.perpendicular())
        return BoneProjection(target[a]+destination*ratio+targetUnit.perpendicular()*(across*thickness),distance,alongOffset+ratio*.5f)
    }

    fun project(point:Point2):Point2 {
        fun smooth(value:Float):Float { val t=value.coerceIn(0f,1f);return t*t*(3-2*t) }
        val uv=sourceCoordinates.getOrPut(point) { torsoCoordinates(point) }
        val base=torsoPoint(uv.x,uv.y)
        val center=(source[0].x+source[1].x+source[2].x+source[3].x)/4
        val left=point.x<center
        val (root,middle,end)=if(left)Triple(0,4,5) else Triple(1,6,7)
        val first=bone(point,root,middle,0f);val second=bone(point,middle,end,.5f)
        val nearest=if(first.distance<=second.distance)first else second
        val jointBlend=smooth((nearest.along-.35f)/.3f)
        val arm=nearest.copy(result=first.result*(1-jointBlend)+second.result*jointBlend)
        val edge=if(left) source[0].x+(source[2].x-source[0].x)*uv.y.coerceIn(0f,1f)
            else source[1].x+(source[3].x-source[1].x)*uv.y.coerceIn(0f,1f)
        val outside=if(left)edge-point.x else point.x-edge
        val fade=(source[1]-source[0]).length()*.04f
        // A hem can extend beyond the calibrated quad. Only give it to a sleeve
        // when it is closer to that sleeve's centerline than to the torso edge.
        // Otherwise a small calibration margin drags the hem toward the wrist.
        val sleeveWeight=smooth((outside-nearest.distance+fade)/(2*fade))
        val blend=sleeveWeight*smooth(outside/fade)*smooth(arm.along/.25f)
        return base*(1-blend)+arm.result*blend
    }

    fun vertices(columns:Int,rows:Int,nextBody:BodyPoints=body):FloatArray? {
        if(!nextBody.usable() || columns !in 1..80 || rows !in 1..80)return null
        target=fitTorso(nextBody)
        outline=nextBody.outline?.takeIf { it.usable() }
        thickness=(target[1]-target[0]).length()/(source[1]-source[0]).length()
        val result=FloatArray((columns+1)*(rows+1)*2)
        var index=0
        for(y in 0..rows)for(x in 0..columns) {
            val point=project(Point2(imageWidth*x.toFloat()/columns,imageHeight*y.toFloat()/rows))
            if(!point.x.isFinite() || !point.y.isFinite())return null
            result[index++]=point.x;result[index++]=point.y
        }
        return result
    }
}
