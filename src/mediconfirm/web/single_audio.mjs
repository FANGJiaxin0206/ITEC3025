export class SingleAudioPlayer {
  constructor(audio, parking, {channel=null}={}) {
    this.audio=audio;this.parking=parking;this.activeId=null;this.channel=channel;
    this.sender=Math.random().toString(36).slice(2);
    audio.onplay=()=>channel?.postMessage({type:'playing',sender:this.sender});
    if(channel)channel.onmessage=e=>{if(e.data?.type==='playing'&&e.data.sender!==this.sender)this.stop();};
  }
  stop(){this.audio.pause();this.activeId=null;this.parking.appendChild(this.audio);}
  async play(clip,slot){
    if(this.activeId===clip.id&&this.audio.paused===false){this.restore(clip,slot);return;}
    this.audio.pause();
    if(!clip.url?.startsWith('/api/audio/'))throw new Error('Audio is unavailable.');
    this.activeId=clip.id;this.audio.src=clip.url;slot.appendChild(this.audio);
    try{await this.audio.play();}catch{if(this.activeId===clip.id)throw new Error('Select Play to listen.');}
  }
  restore(clip,slot){if(this.activeId===clip.id&&this.audio.parentNode!==slot)slot.appendChild(this.audio);}
}
