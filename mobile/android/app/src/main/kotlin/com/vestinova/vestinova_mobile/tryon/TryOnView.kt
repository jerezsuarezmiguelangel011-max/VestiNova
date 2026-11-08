package com.vestinova.vestinova_mobile.tryon

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.graphics.*
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.util.Size
import android.view.View
import androidx.camera.core.*
import androidx.camera.core.Camera
import androidx.camera.core.resolutionselector.AspectRatioStrategy
import androidx.camera.core.resolutionselector.ResolutionSelector
import androidx.camera.core.resolutionselector.ResolutionStrategy
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.core.content.ContextCompat
import com.google.mediapipe.framework.image.BitmapImageBuilder
import com.google.mediapipe.framework.image.ByteBufferExtractor
import com.google.mediapipe.framework.image.MPImage
import com.google.mediapipe.tasks.core.BaseOptions
import com.google.mediapipe.tasks.vision.core.RunningMode
import com.google.mediapipe.tasks.vision.poselandmarker.PoseLandmarker
import com.google.mediapipe.tasks.components.containers.NormalizedLandmark
import io.flutter.embedding.android.FlutterActivity
import io.flutter.plugin.common.*
import io.flutter.plugin.platform.*
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.nio.ByteOrder
import kotlin.math.*

class TryOnFactory(private val activity: FlutterActivity, private val messenger: BinaryMessenger): PlatformViewFactory(StandardMessageCodec.INSTANCE) {
    override fun create(context: Context, viewId: Int, args: Any?): PlatformView = TryOnView(activity,messenger,viewId)
}

// Camera and garment share the SAME oriented bitmap/crop transform. No frames leave Android.
private class TryOnView(private val activity: FlutterActivity, messenger: BinaryMessenger, id: Int): PlatformView {
    private val channel=MethodChannel(messenger,"vestinova/tryon/$id")
    private val surface=FittingSurface(activity)
    private val worker=Executors.newSingleThreadExecutor()
    private val ui=Handler(Looper.getMainLooper())
    @Volatile private var closed=false
    @Volatile private var paused=true
    private var provider: ProcessCameraProvider?=null
    private var analysis: ImageAnalysis?=null
    private var camera: Camera?=null
    private var detector: PoseLandmarker?=null // Accessed only on worker.
    private var lastTime=0L
    private var lastStatus=""
    private var front=true

    init {
        surface.rotationChanged = { rotation -> analysis?.targetRotation=rotation }
        channel.setMethodCallHandler { call,result ->
            when(call.method) {
                "configure" -> try {
                    val args=call.arguments as Map<*,*>
                    val bytes=args["png"] as ByteArray
                    val bounds=BitmapFactory.Options().apply { inJustDecodeBounds=true }
                    BitmapFactory.decodeByteArray(bytes,0,bytes.size,bounds)
                    require(bytes.size<=6*1024*1024 && bounds.outWidth in 1..2048 && bounds.outHeight in 1..2048 && bounds.outMimeType=="image/png")
                    val values=listOf("factor_ancho","factor_alto","offset_x","offset_y").map { (args[it] as Number).toFloat() }
                    require(values.all { it.isFinite() } && values[0] in 0.5f..2.5f && values[1] in 0.5f..2.5f && values[2] in -0.5f..0.5f && values[3] in -0.5f..0.5f)
                    val anchors=(args["anclajes"] as? Map<*,*>)?.let { ImageAnchors.from(it) }
                    val image=BitmapFactory.decodeByteArray(bytes,0,bytes.size) ?: throw IllegalArgumentException()
                    surface.configure(image,values,anchors)
                    result.success(null)
                    if(paused) start()
                } catch(_:Exception) { result.error("asset","No se pudo preparar la imagen transparente de la prenda.",null) }
                "pause" -> { stop();result.success(null) }
                "resume" -> { start();result.success(null) }
                "focus" -> focus(result)
                else -> result.notImplemented()
            }
        }
    }
    private fun status(value:String) {
        ui.post { if(!closed && value!=lastStatus) { lastStatus=value;channel.invokeMethod("state",mapOf("estado" to value)) } }
    }
    private fun start() {
        if(closed || !paused) return
        if(activity.checkSelfPermission(Manifest.permission.CAMERA)!=PackageManager.PERMISSION_GRANTED) { status("permission");return }
        paused=false;status("loading")
        worker.execute {
            try {
                if(detector==null) detector=PoseLandmarker.createFromOptions(activity,PoseLandmarker.PoseLandmarkerOptions.builder()
                    .setBaseOptions(BaseOptions.builder().setModelAssetPath("pose_landmarker_lite.task").build())
                    .setRunningMode(RunningMode.VIDEO).setNumPoses(1).setMinPoseDetectionConfidence(0.6f)
                    .setMinPosePresenceConfidence(0.6f).setMinTrackingConfidence(0.6f).setOutputSegmentationMasks(true).build())
            } catch(_:Exception) { paused=true;status("model_error") }
        }
        val future=ProcessCameraProvider.getInstance(activity)
        future.addListener({
            if(closed || paused) return@addListener
            try {
                provider=future.get()
                front=provider!!.hasCamera(CameraSelector.DEFAULT_FRONT_CAMERA)
                val selector=if(front) CameraSelector.DEFAULT_FRONT_CAMERA else CameraSelector.DEFAULT_BACK_CAMERA
                val resolution=ResolutionSelector.Builder()
                    .setAspectRatioStrategy(AspectRatioStrategy.RATIO_4_3_FALLBACK_AUTO_STRATEGY)
                    .setResolutionStrategy(ResolutionStrategy(Size(1280,960),ResolutionStrategy.FALLBACK_RULE_CLOSEST_LOWER_THEN_HIGHER))
                    .build()
                val useCase=ImageAnalysis.Builder().setResolutionSelector(resolution)
                    .setTargetRotation(surface.display?.rotation ?: 0)
                    .setOutputImageFormat(ImageAnalysis.OUTPUT_IMAGE_FORMAT_RGBA_8888)
                    .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST).build()
                analysis=useCase
                useCase.setAnalyzer(worker) { frame -> process(frame) }
                camera=provider!!.bindToLifecycle(activity,selector,useCase)
            } catch(_:Exception) { stop();status("camera_error") }
        },ContextCompat.getMainExecutor(activity))
    }
    private fun process(frame:ImageProxy) {
        var raw:Bitmap?=null
        var oriented:Bitmap?=null
        try {
            val time=SystemClock.uptimeMillis()
            if(closed || paused || detector==null || time-lastTime<70) return
            lastTime=time
            raw=frame.toBitmap()
            val rotation=Matrix().apply { postRotate(frame.imageInfo.rotationDegrees.toFloat());if(front) postScale(-1f,1f) }
            oriented=Bitmap.createBitmap(raw,0,0,raw.width,raw.height,rotation,true)
            if(oriented!==raw) { raw.recycle();raw=null }
            // MPImage.close() recycles its bitmap. Keep a separate display frame.
            val input=BitmapImageBuilder(requireNotNull(oriented.copy(Bitmap.Config.ARGB_8888,false))).build()
            val result=try { detector!!.detectForVideo(input,time) } finally { input.close() }
            val landmarks=result.landmarks().firstOrNull()
            val anchors=torso(landmarks)
            val display=requireNotNull(oriented)
            val masks=result.segmentationMasks().orElse(emptyList())
            val body=try {
                val pose=body(landmarks,display.width,display.height,surface.longSleeves)
                val mask=masks.firstOrNull()
                if(pose==null || mask==null)pose else pose.copy(outline=outline(mask,pose,display.width,display.height))
            } finally { masks.forEach { it.close() } }
            oriented=null;raw=null // Ownership passes to UI, including the raw==oriented case.
            ui.post {
                if(closed || paused) display.recycle()
                else { status(surface.frame(display,anchors,body,time)) }
            }
        } catch(_:Exception) { status("processing_error") }
        finally { if(oriented!=null) { if(oriented!==raw) oriented.recycle() };raw?.recycle();frame.close() }
    }
    private fun focus(result:MethodChannel.Result) {
        val active=camera
        if(closed || paused || active==null) { result.success("unavailable");return }
        // The center stays the center after crop, rotation and front-camera mirroring.
        val point=SurfaceOrientedMeteringPointFactory(1f,1f).createPoint(.5f,.5f)
        val autofocus=FocusMeteringAction.Builder(point,FocusMeteringAction.FLAG_AF).build()
        val supportsAf=active.cameraInfo.isFocusMeteringSupported(autofocus)
        val mode=if(supportsAf)FocusMeteringAction.FLAG_AF or FocusMeteringAction.FLAG_AE else FocusMeteringAction.FLAG_AE
        val action=FocusMeteringAction.Builder(point,mode).setAutoCancelDuration(3,TimeUnit.SECONDS).build()
        if(!active.cameraInfo.isFocusMeteringSupported(action)) { result.success("unsupported");return }
        try {
            val future=active.cameraControl.startFocusAndMetering(action)
            future.addListener({
                try {
                    val outcome=future.get() // Also observe errors when only exposure is supported.
                    result.success(if(!supportsAf) "fixed_focus" else if(outcome.isFocusSuccessful) "focused" else "not_focused")
                }
                catch(_:Exception) { result.success("unavailable") }
            },ContextCompat.getMainExecutor(activity))
        } catch(_:Exception) { result.success("unavailable") }
    }
    private fun torso(points:List<NormalizedLandmark>?):FloatArray? {
        if(points==null || points.size<25) return null
        val body=listOf(points[11],points[12],points[23],points[24])
        if(body.any { it.visibility().orElse(0f)<.6f || it.presence().orElse(0f)<.6f || it.x() !in 0f..1f || it.y() !in 0f..1f }) return null
        val l=body[0];val r=body[1]
        val sx=(l.x()+r.x())/2;val sy=(l.y()+r.y())/2
        val hy=(body[2].y()+body[3].y())/2
        if(hy-sy<.12f || hypot(l.x()-r.x(),l.y()-r.y())<.08f) return null
        return floatArrayOf(sx,sy,hy,l.x(),l.y(),r.x(),r.y())
    }
    private fun body(points:List<NormalizedLandmark>?,width:Int,height:Int,longSleeves:Boolean):BodyPoints? {
        if(points==null || points.size<25)return null
        val left=if(points[11].x()<points[12].x())listOf(11,23,13,15) else listOf(12,24,14,16)
        val right=if(left[0]==11)listOf(12,24,14,16) else listOf(11,23,13,15)
        val required=if(longSleeves)left+right else left.take(3)+right.take(3)
        if(required.any { val p=points[it];p.visibility().orElse(0f)<.6f || p.presence().orElse(0f)<.6f || p.x() !in 0f..1f || p.y() !in 0f..1f })return null
        fun point(index:Int)=Point2(points[index].x()*width,points[index].y()*height)
        fun sleeve(side:List<Int>):Pair<Point2,Point2> {
            val shoulder=point(side[0]);val elbow=point(side[2])
            return if(longSleeves) elbow to point(side[3])
                else shoulder+(elbow-shoulder)*.28f to shoulder+(elbow-shoulder)*.56f
        }
        val l=sleeve(left);val r=sleeve(right)
        val body=BodyPoints(listOf(point(left[0]),point(right[0]),point(left[1]),point(right[1]),l.first,l.second,r.first,r.second))
        if(!body.usable())return null
        return body
    }
    private fun outline(mask:MPImage,body:BodyPoints,frameWidth:Int,frameHeight:Int):TorsoOutline? = try {
        require(mask.containedImageProperties.any { it.imageFormat==MPImage.IMAGE_FORMAT_VEC32F1 && it.storageType==MPImage.STORAGE_TYPE_BYTEBUFFER })
        val buffer=ByteBufferExtractor.extract(mask).order(ByteOrder.nativeOrder()).asFloatBuffer()
        if(buffer.capacity()!=mask.width*mask.height)null else torsoOutline(body) { point ->
            val x=(point.x/frameWidth*mask.width).toInt();val y=(point.y/frameHeight*mask.height).toInt()
            if(point.x<0 || point.y<0 || x !in 0 until mask.width || y !in 0 until mask.height)Float.NaN
            else buffer.get(y*mask.width+x).takeIf { it in 0f..1f } ?: Float.NaN
        }
    } catch(_:Exception) { null } // Keep pose + garment cut if this device has no usable mask.
    private fun stop() {
        paused=true
        analysis?.clearAnalyzer()
        analysis?.let { provider?.unbind(it) };analysis=null
        camera=null
        surface.clearFrame()
    }
    override fun getView():View=surface
    override fun dispose() {
        if(closed) return
        closed=true;stop();channel.setMethodCallHandler(null);surface.release()
        worker.execute { detector?.close();detector=null };worker.shutdown()
    }
}

private class FittingSurface(context:Context):View(context) {
    var rotationChanged:((Int)->Unit)?=null
    private val paint=Paint(Paint.ANTI_ALIAS_FLAG or Paint.FILTER_BITMAP_FLAG)
    private var camera:Bitmap?=null
    private var garment:Bitmap?=null
    private var placement:GarmentPlacement?=null
    private val smoother=PlacementSmoother()
    private var config=listOf(1.9f,1.2f,0f,0f)
    private var anchors:ImageAnchors?=null
    @Volatile var longSleeves=true
        private set
    private var vertices:FloatArray?=null
    private var projector:GarmentMesh?=null
    private val bodySmoother=BodySmoother()
    init { setBackgroundColor(Color.rgb(25,32,29));contentDescription="Cámara y visualización orientativa de la prenda" }
    fun configure(image:Bitmap,values:List<Float>,points:ImageAnchors?) {
        garment?.recycle();garment=image;config=values;anchors=points;longSleeves=points?.longSleeves ?: true
        placement=null;vertices=null;projector=null;smoother.reset();bodySmoother.reset();invalidate()
    }
    fun frame(image:Bitmap,points:FloatArray?,body:BodyPoints?,time:Long):String {
        camera?.recycle();camera=image
        val cloth=garment
        val calibrated=anchors
        if(calibrated!=null && cloth!=null) {
            val stable=bodySmoother.update(body,time)
            vertices=stable?.let {
                val mesh=projector ?: GarmentMesh(calibrated,it,cloth.width,cloth.height).also { value -> projector=value }
                mesh.vertices(40,40,it)
            }
            placement=null;invalidate()
            return if(vertices!=null) "tracking" else "position_arms"
        }
        val raw=if(points!=null && cloth!=null)projectTorso(points,image.width,image.height,config,cloth.width.toFloat()/cloth.height) else null
        placement=smoother.update(raw,time);invalidate()
        return if(placement!=null) "uncalibrated" else "position"
    }
    fun clearFrame() { camera?.recycle();camera=null;placement=null;vertices=null;smoother.reset();bodySmoother.reset();invalidate() }
    fun release() { clearFrame();garment?.recycle();garment=null;rotationChanged=null }
    override fun onSizeChanged(w:Int,h:Int,oldw:Int,oldh:Int) { super.onSizeChanged(w,h,oldw,oldh);rotationChanged?.invoke(display?.rotation ?: 0) }
    override fun onDraw(canvas:Canvas) {
        super.onDraw(canvas)
        val image=camera ?: return
        val scale=max(width.toFloat()/image.width,height.toFloat()/image.height)
        val dx=(width-image.width*scale)/2;val dy=(height-image.height*scale)/2
        canvas.save();canvas.translate(dx,dy);canvas.scale(scale,scale)
        canvas.drawBitmap(image,0f,0f,paint)
        val placement=placement;val cloth=garment
        val mesh=vertices
        if(mesh!=null && cloth!=null)canvas.drawBitmapMesh(cloth,40,40,mesh,0,null,0,paint)
        else if(placement!=null && cloth!=null) {
                canvas.save();canvas.translate(placement.x,placement.y);canvas.rotate(placement.angle)
                canvas.drawBitmap(cloth,null,RectF(-placement.width/2,-placement.height/2,placement.width/2,placement.height/2),paint)
                canvas.restore()
        }
        canvas.restore()
    }
}
