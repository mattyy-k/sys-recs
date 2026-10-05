#include <algorithm>
#include <array>
#include <cstdint>
#include <cstring>
#include <ctime>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

// Ext2 fields are decoded explicitly; no host structure layout is used.
class Ext2 {
    std::string path;
    std::vector<uint8_t> image;
    uint32_t block_size{}, blocks_count{}, inodes_count{}, first_data{}, bpg{}, ipg{}, inode_size{}, groups{};
    uint32_t gd_start{};
    bool writable{};

    uint16_t u16(size_t p) const { bounds(p, 2); return uint16_t(image[p]) | uint16_t(image[p+1]) << 8; }
    uint32_t u32(size_t p) const { bounds(p, 4); return uint32_t(image[p]) | uint32_t(image[p+1])<<8 | uint32_t(image[p+2])<<16 | uint32_t(image[p+3])<<24; }
    void put16(size_t p, uint16_t v) { bounds(p,2); image[p]=v; image[p+1]=v>>8; }
    void put32(size_t p, uint32_t v) { bounds(p,4); for(int i=0;i<4;i++) image[p+i]=v>>(8*i); }
    void bounds(size_t p,size_t n) const { if(p>image.size() || n>image.size()-p) throw std::runtime_error("image offset out of bounds"); }
    size_t bo(uint32_t b) const { if(b>=blocks_count) throw std::runtime_error("invalid block number"); size_t o=size_t(b)*block_size; bounds(o,block_size); return o; }
    size_t gd(uint32_t g) const { if(g>=groups) throw std::runtime_error("invalid group"); return size_t(gd_start)+g*32; }
    uint32_t inode_table(uint32_t n) const { uint32_t g=(n-1)/ipg; return u32(gd(g)+8); }
    size_t io(uint32_t n) const { if(n==0 || n>inodes_count) throw std::runtime_error("invalid inode number"); size_t p=size_t(inode_table(n))*block_size+size_t((n-1)%ipg)*inode_size; bounds(p,inode_size); return p; }
    uint32_t mode(uint32_t n) const { return u16(io(n)); }
    uint64_t size(uint32_t n) const { size_t p=io(n); uint64_t s=u32(p+4); if((mode(n)&0xf000)==0x8000 && inode_size>=112) s |= uint64_t(u32(p+108))<<32; return s; }
    std::vector<uint32_t> blocks(uint32_t n) const {
        size_t p=io(n); uint64_t count=(size(n)+block_size-1)/block_size;
        if(count>12ull+block_size/4+(uint64_t(block_size)/4)*(block_size/4)) throw std::runtime_error("file exceeds supported double-indirect range");
        std::vector<uint32_t> out; out.reserve(count);
        for(int i=0;i<12 && out.size()<count;i++) out.push_back(u32(p+40+4*i));
        auto add=[&](uint32_t ptr, uint64_t limit) { if(!ptr) { while(out.size()<std::min<uint64_t>(count,limit)) out.push_back(0); return; } size_t q=bo(ptr); for(uint32_t i=0;i<block_size/4 && out.size()<count;i++) out.push_back(u32(q+4*i)); };
        if(out.size()<count) add(u32(p+88),12+block_size/4);
        if(out.size()<count) { uint32_t root=u32(p+92); if(!root) throw std::runtime_error("sparse double-indirect file unsupported"); size_t q=bo(root); for(uint32_t i=0;i<block_size/4 && out.size()<count;i++) add(u32(q+4*i),count); }
        if(out.size()<count) out.resize(count,0);
        return out;
    }
    std::vector<uint8_t> read(uint32_t n) const { uint64_t sz=size(n); if(sz>image.size()*16ull) throw std::runtime_error("implausible inode size"); auto bs=blocks(n); std::vector<uint8_t> out(sz); for(size_t i=0;i<bs.size();i++) if(bs[i]) { size_t off=bo(bs[i]); size_t len=std::min<size_t>(block_size,sz-i*block_size); std::copy_n(image.begin()+off,len,out.begin()+i*block_size); } return out; }
    struct Entry { uint32_t ino; uint8_t type; std::string name; };
    std::vector<Entry> entries(uint32_t n) const { auto data=read(n); std::vector<Entry> out; for(size_t p=0;p<data.size();) { if(data.size()-p<8) throw std::runtime_error("truncated directory entry"); uint32_t ino=data[p]|uint32_t(data[p+1])<<8|uint32_t(data[p+2])<<16|uint32_t(data[p+3])<<24; uint16_t rec=data[p+4]|uint16_t(data[p+5])<<8; uint8_t nl=data[p+6], ty=data[p+7]; if(rec<8 || rec%4 || rec>data.size()-p || nl>rec-8) throw std::runtime_error("invalid directory record"); if(ino) out.push_back({ino,ty,std::string(reinterpret_cast<char*>(data.data()+p+8),nl)}); p+=rec; } return out; }
    uint32_t lookup(uint32_t dir,const std::string& name) const { for(auto&e:entries(dir)) if(e.name==name) return e.ino; throw std::runtime_error("path not found: "+name); }
    uint32_t resolve(const std::string& p) const { uint32_t n=2; size_t i=0; while(i<p.size()) { while(i<p.size() && p[i]=='/')i++; if(i==p.size())break; size_t j=p.find('/',i); std::string part=p.substr(i,j==std::string::npos?j:j-i); if(part!=".") n=lookup(n,part); i=j==std::string::npos?p.size():j; } return n; }
    void tree(uint32_t n,const std::string& p,std::set<uint32_t>& active) const { for(auto&e:entries(n)) { if(e.name=="."||e.name=="..") continue; std::string child=p=="/"?"/"+e.name:p+"/"+e.name; const char* t=(e.type==2||((mode(e.ino)&0xf000)==0x4000))?"directory":(e.type==7?"symlink":"file"); std::cout<<e.ino<<"\t"<<t<<"\t"<<child<<"\n"; if((mode(e.ino)&0xf000)==0x4000 && active.insert(e.ino).second) { tree(e.ino,child,active); active.erase(e.ino); } } }
    uint32_t alloc() { if(!writable) throw std::runtime_error("image is read-only"); for(uint32_t g=0;g<groups;g++) { size_t d=gd(g); uint32_t free=u16(d+12), bm=u32(d); if(!free) continue; size_t q=bo(bm); uint32_t first=first_data+g*bpg; uint32_t valid=std::min(bpg,blocks_count-first); for(uint32_t bit=0;bit<valid;bit++) if(!(image[q+bit/8]&(1u<<(bit%8)))) { image[q+bit/8]|=1u<<(bit%8); put16(d+12,free-1); put32(1024+12,u32(1024+12)-1); return first+bit; } } throw std::runtime_error("no free blocks"); }
    void release(uint32_t b) { if(!b)return; uint32_t g=(b-first_data)/bpg; size_t d=gd(g), q=bo(u32(d)); uint32_t bit=b-(first_data+g*bpg); if(image[q+bit/8]&(1u<<(bit%8))) { image[q+bit/8]&=~(1u<<(bit%8)); put16(d+12,u16(d+12)+1); put32(1024+12,u32(1024+12)+1); } }
    void write_file(uint32_t n,const std::vector<uint8_t>& data,bool append) { if(!writable) throw std::runtime_error("image is read-only"); if((mode(n)&0xf000)!=0x8000) throw std::runtime_error("target is not a regular file"); std::vector<uint8_t> content=append?read(n):std::vector<uint8_t>{}; content.insert(content.end(),data.begin(),data.end()); uint64_t need=(content.size()+block_size-1)/block_size; if(need>12ull+block_size/4) throw std::runtime_error("writes above direct plus single-indirect are unsupported"); size_t p=io(n); auto old=blocks(n); old.resize((size(n)+block_size-1)/block_size); std::vector<uint32_t> nb(need); for(size_t i=0;i<std::min(nb.size(),old.size());i++) nb[i]=old[i]; for(auto&b:nb) if(!b)b=alloc();
        for(size_t i=0;i<nb.size();i++) { size_t q=bo(nb[i]); size_t len=std::min<size_t>(block_size,content.size()-i*block_size); std::fill(image.begin()+q,image.begin()+q+block_size,0); std::copy_n(content.begin()+i*block_size,len,image.begin()+q); }
        uint32_t ind=0; if(nb.size()>12) { ind=u32(p+88); if(!ind) ind=alloc(); size_t q=bo(ind); std::fill(image.begin()+q,image.begin()+q+block_size,0); for(size_t i=12;i<nb.size();i++) put32(q+4*(i-12),nb[i]); } else { ind=u32(p+88); }
        for(size_t i=nb.size();i<old.size();i++) release(old[i]);
        if(old.size()>12 && nb.size()<=12) { release(ind); ind=0; }
        for(size_t i=0;i<12;i++) put32(p+40+4*i,i<nb.size()?nb[i]:0);
        put32(p+88,ind); put32(p+4,uint32_t(content.size())); if(inode_size>=112) put32(p+108,uint32_t(uint64_t(content.size())>>32)); put32(p+28,uint32_t((nb.size()+(ind?1:0))*block_size/512)); uint32_t now=static_cast<uint32_t>(std::time(nullptr)); put32(p+8,now); put32(p+12,now); put32(p+16,now);
        std::ofstream f(path,std::ios::binary|std::ios::trunc); if(!f) throw std::runtime_error("cannot write image"); f.write(reinterpret_cast<char*>(image.data()),image.size()); if(!f) throw std::runtime_error("image write failed");
    }
public:
    Ext2(std::string file,bool rw):path(std::move(file)),writable(rw) { std::ifstream f(path,std::ios::binary); if(!f) throw std::runtime_error("cannot open image: "+path); image.assign(std::istreambuf_iterator<char>(f),{}); if(image.size()<2048) throw std::runtime_error("image too small"); if(u16(1024+56)!=0xef53) throw std::runtime_error("bad ext2 magic"); uint32_t log=u32(1024+24); if(log>2) throw std::runtime_error("unsupported block size"); block_size=1024u<<log; inodes_count=u32(1024); blocks_count=u32(1024+4); first_data=u32(1024+20); bpg=u32(1024+32); ipg=u32(1024+40); inode_size=u32(1024+76)?u16(1024+88):128; if(!bpg||!ipg||inode_size<128||inode_size>block_size) throw std::runtime_error("invalid ext2 geometry"); groups=std::max((blocks_count-first_data+bpg-1)/bpg,(inodes_count+ipg-1)/ipg); gd_start=(first_data+1)*block_size; bounds(gd_start,size_t(groups)*32); }
    void info() const { std::cout<<"inodes: "<<inodes_count<<"\nblocks: "<<blocks_count<<"\nfree blocks: "<<u32(1024+12)<<"\nfree inodes: "<<u32(1024+16)<<"\nblock size: "<<block_size<<"\nblocks/group: "<<bpg<<"\ninodes/group: "<<ipg<<"\ninode size: "<<inode_size<<"\nmagic: 0x"<<std::hex<<u16(1080)<<std::dec<<"\nrevision: "<<u32(1024+76)<<"\ncompat: 0x"<<std::hex<<u32(1024+92)<<" incompat: 0x"<<u32(1024+96)<<" ro_compat: 0x"<<u32(1024+100)<<std::dec<<"\n"; }
    void group_info() const { for(uint32_t g=0;g<groups;g++){size_t p=gd(g);std::cout<<"group "<<g<<": block_bitmap="<<u32(p)<<" inode_bitmap="<<u32(p+4)<<" inode_table="<<u32(p+8)<<" free_blocks="<<u16(p+12)<<" free_inodes="<<u16(p+14)<<" directories="<<u16(p+16)<<"\n";} }
    void show_tree() const {std::set<uint32_t>s{2};std::cout<<"2\tdirectory\t/\n";tree(2,"/",s);}
    void cat(const std::string&p) const { auto d=read(resolve(p));std::cout.write(reinterpret_cast<const char*>(d.data()),d.size()); }
    void update(const std::string&p,const std::string& input,bool append) { std::ifstream f(input,std::ios::binary);std::vector<uint8_t>d;if(f)d.assign(std::istreambuf_iterator<char>(f),{});else d.assign(input.begin(),input.end());write_file(resolve(p),d,append); }
};
int main(int argc,char**argv){try{if(argc<3){std::cerr<<"usage: ext2 <info|groups|tree|cat|overwrite|append> IMAGE [PATH] [DATA_OR_FILE]\n";return 2;}std::string cmd=argv[1];bool rw=cmd=="overwrite"||cmd=="append";Ext2 fs(argv[2],rw);if(cmd=="info")fs.info();else if(cmd=="groups")fs.group_info();else if(cmd=="tree")fs.show_tree();else if(cmd=="cat"&&argc==4)fs.cat(argv[3]);else if((cmd=="overwrite"||cmd=="append")&&argc==5)fs.update(argv[3],argv[4],cmd=="append");else throw std::runtime_error("invalid command arguments");return 0;}catch(const std::exception&e){std::cerr<<"ext2: "<<e.what()<<"\n";return 1;}}
