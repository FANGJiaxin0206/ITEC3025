// Own the stream and discard late permission responses after close/navigation.
export class DesktopCamera {
  constructor(video, {mediaDevices = globalThis.navigator?.mediaDevices, changed = () => {}} = {}) {
    this.video = video;
    this.mediaDevices = mediaDevices;
    this.changed = changed;
    this.stream = null;
    this.generation = 0;
    this.opening = false;
  }
  stop() {
    this.generation++;
    this.opening = false;
    if (this.stream) this.stream.getTracks().forEach(track => track.stop());
    this.stream = null;
    this.video.pause();
    this.video.srcObject = null;
    this.changed(false, false);
  }
  async open() {
    this.stop();
    if (!this.mediaDevices?.getUserMedia) throw new Error('Camera access is unavailable. Open this app on localhost or use an HTTPS connection. You can also choose an image.');
    const generation = this.generation;
    this.opening = true;
    this.changed(false, true);
    let stream;
    try {
      stream = await this.mediaDevices.getUserMedia({video: {width: {ideal: 1280}, height: {ideal: 720}}, audio: false});
      if (generation !== this.generation) {stream.getTracks().forEach(track => track.stop());return false;}
      this.stream = stream;
      this.video.srcObject = stream;
      await this.video.play();
      if (generation !== this.generation) return false;
      for (const track of stream.getVideoTracks()) track.onended = () => {
        if (this.stream === stream) this.stop();
      };
      this.opening = false;
      this.changed(true, false);
      return true;
    } catch (error) {
      if (generation !== this.generation) return false;
      if (stream) stream.getTracks().forEach(track => track.stop());
      this.stop();
      const messages = {
        NotAllowedError: 'Camera permission was denied. Allow camera access in your browser site settings, then try again.',
        NotFoundError: 'No camera was found. Connect a camera or choose an image.',
        NotReadableError: 'The camera is busy or unavailable. Close other camera apps, then try again.'
      };
      throw new Error(messages[error.name] || 'The camera could not start. Close it and try again, or choose an image.');
    }
  }
  async capture(canvas) {
    if (!this.stream || !this.video.videoWidth || !this.video.videoHeight || this.video.readyState < 2) {
      throw new Error('The camera is not ready yet. Wait for the live preview, then take the photo.');
    }
    const generation = this.generation;
    canvas.width = this.video.videoWidth;
    canvas.height = this.video.videoHeight;
    canvas.getContext('2d').drawImage(this.video, 0, 0);
    const photo = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', .9));
    if (generation !== this.generation) return null;
    if (!photo) throw new Error('The photo could not be captured. Please try again.');
    this.stop();
    return photo;
  }
}
