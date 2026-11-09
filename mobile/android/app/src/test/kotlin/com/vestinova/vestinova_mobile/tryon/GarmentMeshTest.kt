package com.vestinova.vestinova_mobile.tryon

import org.junit.Assert.*
import org.junit.Test

class GarmentMeshTest {
    private val source=listOf(Point2(.32f,.2f),Point2(.68f,.2f),Point2(.35f,.86f),Point2(.65f,.86f),
        Point2(.22f,.48f),Point2(.12f,.85f),Point2(.78f,.48f),Point2(.88f,.85f))
    private val anchors=ImageAnchors(source,true)
    private val body=BodyPoints(listOf(Point2(300f,200f),Point2(700f,200f),Point2(330f,700f),Point2(670f,700f),
        Point2(240f,430f),Point2(180f,650f),Point2(760f,430f),Point2(820f,650f)))
    private fun assertPoint(expected:Point2,actual:Point2) {
        assertEquals(expected.x,actual.x,.02f);assertEquals(expected.y,actual.y,.02f)
    }
    @Test fun alignsTorsoAndSleeveLandmarksInsteadOfTheWholePhotoRectangle() {
        val mesh=GarmentMesh(anchors,body,1000,1000)
        source.forEachIndexed { i,p ->
            val expected=when(i) { 2 -> body.points[i]+Point2(-7.65f,0f);3 -> body.points[i]+Point2(7.65f,0f);else -> body.points[i] }
            assertPoint(expected,mesh.project(p*1000f))
        }
    }
    @Test fun movesCuffToBentWristWhileKeepingTheCollarAndWaistInPlace() {
        val bent=BodyPoints(body.points.toMutableList().apply { this[5]=Point2(390f,350f);this[7]=Point2(610f,350f) })
        val mesh=GarmentMesh(anchors,bent,1000,1000)
        assertPoint(bent.points[5],mesh.project(source[5]*1000f))
        assertPoint(bent.points[7],mesh.project(source[7]*1000f))
        assertPoint(Point2(500f,200f),mesh.project(Point2(500f,200f)))
        assertPoint(Point2(500f,700f),mesh.project(Point2(500f,860f)))
    }
    @Test fun usesSourceImageDimensionsForNonSquarePhotos() {
        val mesh=GarmentMesh(anchors,body,800,1200)
        source.forEachIndexed { i,p ->
            val expected=when(i) { 2 -> body.points[i]+Point2(-7.65f,0f);3 -> body.points[i]+Point2(7.65f,0f);else -> body.points[i] }
            assertPoint(expected,mesh.project(Point2(p.x*800,p.y*1200)))
        }
        val grid=mesh.vertices(40,40)!!
        assertEquals(41*41*2,grid.size);assertTrue(grid.all { it.isFinite() })
    }
    @Test fun reusesSourceCoordinatesButUpdatesEveryTargetForTheNextFrame() {
        val mesh=GarmentMesh(anchors,body,1000,1000)
        val first=mesh.vertices(40,40)!!
        val moved=BodyPoints(body.points.map { it+Point2(30f,20f) })
        val next=mesh.vertices(40,40,moved)!!
        for(i in first.indices step 2) {
            assertEquals(30f,next[i]-first[i],.1f);assertEquals(20f,next[i+1]-first[i+1],.1f)
        }
    }
    @Test fun rejectsCollapsedReversedOrMissingBodyInsteadOfDistortingThePng() {
        for(invalid in listOf(BodyPoints(emptyList()),BodyPoints(body.points.toMutableList().apply { this[1]=this[0] }),
            BodyPoints(body.points.toMutableList().apply { this[3]=Point2(200f,700f) }),
            BodyPoints(body.points.toMutableList().apply { this[2]=Point2(340f,100f) }))) {
            assertFalse(invalid.usable());assertNull(GarmentMesh(anchors,invalid,1000,1000).vertices(40,40))
        }
    }
    @Test fun requiresThreeFramesAndDropsLostOrAbruptPoses() {
        val smooth=BodySmoother()
        assertNull(smooth.update(body,100));assertNull(smooth.update(body,170));assertNotNull(smooth.update(body,240))
        val moved=BodyPoints(body.points.map { it+Point2(10f,0f) })
        val tracked=smooth.update(moved,310)!!
        assertTrue(tracked.points[0].x>300 && tracked.points[0].x<310)
        assertNull(smooth.update(null,380));assertNull(smooth.update(body,450))
        smooth.update(body,520);smooth.update(body,590)
        assertNull(smooth.update(BodyPoints(body.points.map { it+Point2(600f,0f) }),660))
        assertNull(smooth.update(body,1500))
    }
    @Test fun checksDownloadedAnchorCoordinatesAndSleeveType() {
        val payload=ANCHOR_KEYS.zip(source).associate { (key,p) -> key to mapOf("x" to p.x,"y" to p.y) }.toMutableMap<String,Any>()
        payload["manga"]="LARGA"
        assertTrue(ImageAnchors.from(payload).longSleeves)
        for((key,value) in listOf("manga" to "INVALID", "hombro_izq" to mapOf("x" to Float.NaN,"y" to .2f),
            "manga_izq_media" to mapOf("x" to .32f,"y" to .2f))) {
            try { ImageAnchors.from(payload+mapOf(key to value));fail("Invalid anchors accepted") } catch(_:IllegalArgumentException) { }
        }
    }
    @Test fun narrowHipJointsDoNotTurnAStraightGarmentIntoAnHourglass() {
        val narrow=BodyPoints(body.points.toMutableList().apply {
            this[2]=Point2(400f,700f);this[3]=Point2(600f,700f)
        })
        val mesh=GarmentMesh(anchors,narrow,1000,1000)
        val left=mesh.project(source[2]*1000f);val right=mesh.project(source[3]*1000f)
        val originalRatio=(source[3]-source[2]).length()/(source[1]-source[0]).length()
        assertTrue("Hip joints are internal landmarks, not the garment silhouette",(right-left).length()>=400f*originalRatio-.1f)
        assertEquals(500f,(left.x+right.x)/2,.02f)
    }
    @Test fun preservesWiderHipsAndTheWidthGuardAlsoAppliesToFollowingFrames() {
        val wide=BodyPoints(body.points.toMutableList().apply {
            this[2]=Point2(270f,700f);this[3]=Point2(730f,700f)
        })
        val mesh=GarmentMesh(anchors,wide,1000,1000)
        assertPoint(wide.points[2]+Point2(-10.35f,0f),mesh.project(source[2]*1000f))
        assertPoint(wide.points[3]+Point2(10.35f,0f),mesh.project(source[3]*1000f))
        val narrow=BodyPoints(body.points.toMutableList().apply {
            this[2]=Point2(440f,700f);this[3]=Point2(640f,700f)
        })
        assertNotNull(mesh.vertices(40,40,narrow))
        val left=mesh.project(source[2]*1000f);val right=mesh.project(source[3]*1000f)
        assertTrue((right-left).length()>=333.2f)
        assertEquals(540f,(left.x+right.x)/2,.02f)
    }
    @Test fun hemOutsideTheCalibratedQuadMustNotFollowTheWrist() {
        val photoPoints=listOf(Point2(.31f,.23f),Point2(.70f,.23f),Point2(.32f,.90f),Point2(.68f,.90f),
            Point2(.215f,.54f),Point2(.17f,.895f),Point2(.785f,.54f),Point2(.825f,.895f))
        val photo=ImageAnchors(photoPoints,true)
        val extended=GarmentMesh(photo,body,1000,1000)
        val bent=BodyPoints(body.points.toMutableList().apply { this[5]=Point2(390f,350f);this[7]=Point2(610f,350f) })
        val bentMesh=GarmentMesh(photo,bent,1000,1000)
        // The actual hem can extend slightly beyond the four marked torso points.
        for(x in listOf(.29f,.71f))assertPoint(extended.project(Point2(x*1000,880f)),bentMesh.project(Point2(x*1000,880f)))
    }
}
