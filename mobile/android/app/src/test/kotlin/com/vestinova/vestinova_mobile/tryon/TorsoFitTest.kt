package com.vestinova.vestinova_mobile.tryon

import org.junit.Assert.*
import org.junit.Test
import kotlin.math.*

class TorsoFitTest {
    private val photo=listOf(Point2(.31f,.23f),Point2(.70f,.23f),Point2(.32f,.90f),Point2(.68f,.90f),
        Point2(.215f,.54f),Point2(.17f,.895f),Point2(.785f,.54f),Point2(.825f,.895f))
    private val anchors=ImageAnchors(photo,true)
    private val pose=BodyPoints(listOf(Point2(300f,200f),Point2(700f,200f),Point2(340f,700f),Point2(660f,700f),
        Point2(240f,430f),Point2(180f,650f),Point2(760f,430f),Point2(820f,650f)))
    private val neckline=Point2(505f,80f)
    private fun point(expected:Point2,actual:Point2) {
        assertEquals(expected.x,actual.x,.03f);assertEquals(expected.y,actual.y,.03f)
    }
    @Test fun upperProjectionRestoresThePreviousCollarWithoutIndependentCompression() {
        for(height in listOf(350f,500f,650f)) {
            val body=pose.copy(points=pose.points.toMutableList().apply { this[2]=Point2(340f,200+height);this[3]=Point2(660f,200+height) })
            val mesh=GarmentMesh(anchors,body,1000,1000)
            assertEquals(200f+(80f-230f)/670f*height,mesh.project(neckline).y,.03f)
            point(body.points[0],mesh.project(photo[0]*1000f))
            point(body.points[1],mesh.project(photo[1]*1000f))
            point(body.points[5],mesh.project(photo[5]*1000f))
        }
    }
    @Test fun upperProjectionMovesWithTheTorsoAndKeepsTheSleeveAnchors() {
        val angle=.2f
        fun transform(p:Point2)=Point2(p.x*cos(angle)-p.y*sin(angle)+50,p.x*sin(angle)+p.y*cos(angle)+30)
        val original=GarmentMesh(anchors,pose,1000,1000)
        val moved=GarmentMesh(anchors,pose.copy(points=pose.points.map(::transform)),1000,1000)
        for(p in listOf(neckline,Point2(450f,170f),Point2(550f,170f)))point(transform(original.project(p)),moved.project(p))
    }
    @Test fun shirtGetsSomeEaseWithoutShrinkingTheCutOrMovingSleeveEndpoints() {
        val mesh=GarmentMesh(anchors,pose,1000,1000)
        val left=mesh.project(photo[2]*1000f);val right=mesh.project(photo[3]*1000f)
        assertEquals(400f*(.36f/.39f)*1.045f,(right-left).length(),.05f)
        point(Point2(500f,700f),mesh.project(Point2(500f,900f)))
        for(i in listOf(0,1,4,5,6,7))point(pose.points[i],mesh.project(photo[i]*1000f))
    }
    @Test fun torsoMaskFollowsVisibleSidesButPreservesShouldersAndSleeves() {
        val outline=torsoOutline(pose) { p -> if(p.x in 280f..720f)1f else 0f }!!
        assertTrue(outline.usable())
        val withMask=GarmentMesh(anchors,pose.copy(outline=outline),1000,1000)
        val left=withMask.project(Point2(315f,565f));val right=withMask.project(Point2(690f,565f))
        assertTrue(left.x<280f && right.x>720f)
        for(i in listOf(0,1,4,5,6,7))point(pose.points[i],withMask.project(photo[i]*1000f))
        val bent=pose.copy(outline=outline,points=pose.points.toMutableList().apply { this[5]=Point2(390f,350f);this[7]=Point2(610f,350f) })
        val moved=GarmentMesh(anchors,bent,1000,1000)
        point(withMask.project(Point2(290f,880f)),moved.project(Point2(290f,880f)))
    }
    @Test fun rejectsMergedArmsEmptyAmbiguousAndOutOfFrameMasks() {
        assertNull(torsoOutline(pose) { 1f })
        assertNull(torsoOutline(pose) { 0f })
        assertNull(torsoOutline(pose) { .5f })
        assertNull(torsoOutline(pose) { Float.NaN })
        assertNull(torsoOutline(pose) { p -> if(p.y>400f && p.y<600f && p.x in 280f..720f)1f else 0f })
    }
    @Test fun samplesInTheSameRotatedCoordinatesAsTheShoulders() {
        val angle=.25f;val cos=cos(angle);val sin=sin(angle)
        fun rotate(p:Point2)=Point2(p.x*cos-p.y*sin,p.x*sin+p.y*cos)
        val tilted=pose.copy(points=pose.points.map(::rotate))
        val straight=torsoOutline(pose) { p -> if(p.x in 280f..720f)1f else 0f }!!
        val rotated=torsoOutline(tilted) { p -> if(p.x*cos+p.y*sin in 280f..720f)1f else 0f }!!
        straight.widths.zip(rotated.widths).forEach { (a,b) -> point(a,b) }
    }
    @Test fun smoothsOutlineWidthsAndDropsThemWhenTheMaskIsLost() {
        val outline=TorsoOutline(List(5) { Point2(.6f,.6f) })
        val smooth=BodySmoother()
        smooth.update(pose,100);smooth.update(pose,170);smooth.update(pose,240)
        val next=smooth.update(pose.copy(outline=outline),310)!!
        assertTrue(next.outline!!.widths[2].x in .51f.. .59f)
        assertNull(smooth.update(pose,380)!!.outline)
    }
    @Test fun collarHeightDoesNotCollapseIntoAHorizontalStrip() {
        val mesh=GarmentMesh(anchors,pose,1000,1000)
        val top=mesh.project(Point2(505f,80f));val bottom=mesh.project(Point2(505f,200f))
        val left=mesh.project(Point2(470f,140f));val right=mesh.project(Point2(540f,140f))
        val originalAspect=120f/70f
        assertTrue("Regression: collar flattened independently of its width",(bottom-top).length()/(right-left).length()>=originalAspect*.65f)
    }
}
