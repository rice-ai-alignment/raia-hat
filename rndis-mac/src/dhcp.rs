//! DHCP for the single USB peer; never connected to the Mac's LAN.
pub fn reply(f: &[u8], host: [u8; 4], peer: [u8; 4], mac: [u8; 6]) -> Option<Vec<u8>> {
    if f.len() < 14+20+8+240 || f.get(12..14)? != [8,0] { return None; }
    let ihl = ((f[14] & 15) as usize)*4;
    if f[14] >> 4 != 4 || ihl < 20 || f[23] != 17 { return None; }
    let udp = 14+ihl;
    if f.get(udp..udp+4)? != [0,68,0,67] { return None; }
    let udp_len = u16::from_be_bytes(f.get(udp+4..udp+6)?.try_into().ok()?) as usize;
    if udp_len < 248 { return None; }
    let b = f.get(udp+8..udp+udp_len)?;
    if b[0] != 1 || b[1] != 1 || b[2] != 6 || b[236..240] != [99,130,83,99] || b[28..34] == mac { return None; }
    let mut kind = 0;
    let mut pos = 240;
    while pos < b.len() {
        let code=b[pos]; pos+=1;
        if code==255 { break; }
        if code==0 { continue; }
        let n=*b.get(pos)? as usize; pos+=1;
        let value=b.get(pos..pos+n)?; pos+=n;
        if code==53 && n==1 { kind=value[0]; }
        if code==54 && value!=host { return None; }
    }
    let response_kind=match kind { 1=>2, 3=>5, _=>return None };
    let mut boot=vec![0u8;240];
    boot[0..4].copy_from_slice(&[2,1,6,0]);
    boot[4..8].copy_from_slice(&b[4..8]);
    boot[10]=0x80;
    boot[16..20].copy_from_slice(&peer);
    boot[20..24].copy_from_slice(&host);
    boot[28..44].copy_from_slice(&b[28..44]);
    boot[236..240].copy_from_slice(&[99,130,83,99]);
    boot.extend_from_slice(&[53,1,response_kind,54,4]); boot.extend_from_slice(&host);
    boot.extend_from_slice(&[51,4]); boot.extend_from_slice(&86400u32.to_be_bytes());
    boot.extend_from_slice(&[1,4,255,255,255,0,255]);
    let udp_size=8+boot.len();
    let mut ip=vec![0u8;20]; ip[0]=0x45;
    ip[2..4].copy_from_slice(&((20+udp_size) as u16).to_be_bytes());
    ip[8]=64;ip[9]=17;ip[12..16].copy_from_slice(&host);ip[16..20].fill(255);
    let mut sum:u32=ip.chunks_exact(2).map(|x| u16::from_be_bytes([x[0],x[1]]) as u32).sum();
    while sum>>16 != 0 { sum=(sum&65535)+(sum>>16); }
    ip[10..12].copy_from_slice(&(!(sum as u16)).to_be_bytes());
    let mut out=vec![255u8;6]; out.extend_from_slice(&mac);out.extend_from_slice(&[8,0]);out.extend_from_slice(&ip);
    out.extend_from_slice(&[0,67,0,68]);out.extend_from_slice(&(udp_size as u16).to_be_bytes());out.extend_from_slice(&[0,0]);out.extend_from_slice(&boot);
    Some(out)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn request(kind:u8)->Vec<u8> {
        let mut f=vec![0u8;14+20+8+244]; f[12..14].copy_from_slice(&[8,0]);f[14]=0x45;f[23]=17;
        f[34..38].copy_from_slice(&[0,68,0,67]);f[38..40].copy_from_slice(&252u16.to_be_bytes());
        let b=&mut f[42..];b[0..4].copy_from_slice(&[1,1,6,0]);b[4..8].copy_from_slice(&[1,2,3,4]);b[28..34].copy_from_slice(&[6,5,4,3,2,1]);b[236..244].copy_from_slice(&[99,130,83,99,53,1,kind,255]);f
    }
    #[test] fn discover_offer_and_request_ack() {
        for (kind,answer) in [(1,2),(3,5)] {
            let r=reply(&request(kind),[192,168,77,1],[192,168,77,2],[2,3,4,5,6,7]).unwrap();
            assert_eq!(&r[34..38],&[0,67,0,68]);assert_eq!(&r[42+4..42+8],&[1,2,3,4]);
            assert_eq!(&r[42+16..42+20],&[192,168,77,2]);assert_eq!(r[42+242],answer);
            let sum:u32=r[14..34].chunks_exact(2).map(|x|u16::from_be_bytes([x[0],x[1]]) as u32).sum();
            assert_eq!((sum&65535)+(sum>>16),65535);
        }
    }
    #[test] fn rejects_truncation_and_other_traffic() {
        let f=request(1);
        for length in 0..f.len() { assert!(reply(&f[..length],[192,168,77,1],[192,168,77,2],[2;6]).is_none()); }
        let mut f=request(1);f[35]=69;assert!(reply(&f,[192,168,77,1],[192,168,77,2],[2;6]).is_none());
    }
}
