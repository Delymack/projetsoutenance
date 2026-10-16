import puppeteer from 'puppeteer-core';

const rows = [
  ['Choix et définition du sujet', 1, 1, '#1a73e8'],
  ['Collecte des informations et identification des besoins', 2, 2, '#1a73e8'],
  ['Analyse de l\u2019existant', 3, 3, '#1877c9'],
  ['Définition des besoins fonctionnels', 4, 4, '#1877c9'],
  ['Conception et modélisation', 5, 6, '#137333'],
  ['Conception de la base de données', 7, 7, '#137333'],
  ['Préparation de l\u2019environnement de développement', 8, 8, '#137333'],
  ['Développement du backend', 9, 11, '#7B1FA2'],
  ['Développement des fonctionnalités principales', 12, 13, '#7B1FA2'],
  ['Mise en place et intégration de l\u2019interface', 14, 15, '#7B1FA2'],
  ['Tests et corrections', 16, 16, '#B06000'],
  ['Documentation et rédaction du mémoire', 17, 18, '#0b7285'],
  ['Préparation de la soutenance', 19, 19, '#0b7285'],
];

const LB=470, PAD=20, WK=52, weeks=19;
const rowH=38, headH=56, top=PAD+headH;
const TW=LB+PAD*2+weeks*WK;
const H=top+rows.length*rowH+PAD;

function esc(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
const x0=LB+PAD;
const wx=w=> x0+(w-1)*WK;

let s=`<svg xmlns="http://www.w3.org/2000/svg" width="${TW}" height="${H}" font-family="Helvetica, Arial, sans-serif">`;
s+=`<rect width="${TW}" height="${H}" fill="#ffffff"/>`;
// title band
s+=`<rect x="0" y="0" width="${TW}" height="${PAD+headH-14}" fill="#F8F9FA"/>`;
s+=`<text x="${PAD}" y="${PAD+30}" font-size="22" font-weight="700" fill="#202124">Diagramme de Gantt — planning prévisionnel du projet (19 semaines)</text>`;
// week header
for(let w=1;w<=weeks;w++){
  const gx=wx(w);
  s+=`<rect x="${gx}" y="${top-headH+14}" width="${WK}" height="${headH-14}" fill="${w%2?'#EEF3FB':'#F8FAFD'}" stroke="#D2D6DC"/>`;
  s+=`<text x="${gx+WK/2}" y="${top-8}" text-anchor="middle" font-size="13" font-weight="600" fill="#3c4043">S${w}</text>`;
}
// grid + rows
for(let i=0;i<rows.length;i++){
  const [label,a,b,color]=rows[i];
  const y=top+i*rowH;
  if(i%2) s+=`<rect x="${PAD}" y="${y}" width="${LB}" height="${rowH}" fill="#FAFBFC"/>`;
  for(let w=1;w<=weeks;w++){
    if(w%2) s+=`<rect x="${wx(w)}" y="${y}" width="${WK}" height="${rowH}" fill="#F3F6FA"/>`;
  }
  s+=`<line x1="${PAD}" y1="${y+rowH}" x2="${TW-PAD}" y2="${y+rowH}" stroke="#E3E6EA"/>`;
  s+=`<text x="${PAD+8}" y="${y+rowH/2+5}" font-size="13.5" fill="#202124">${i+1}. ${esc(label)}</text>`;
  const bx=wx(a), bw=(b-a+1)*WK-8, by=y+8, bh=rowH-16;
  s+=`<rect x="${bx+4}" y="${by}" width="${bw}" height="${bh}" rx="6" fill="${color}" opacity="0.9"/>`;
  const dur = a===b ? `S${a}` : `S${a}–S${b}`;
  s+=`<text x="${bx+4+bw+8}" y="${y+rowH/2+5}" font-size="12" fill="#5f6368">${dur}</text>`;
}
// left header for activities
s+=`<rect x="${PAD}" y="${top-headH+14}" width="${LB}" height="${headH-14}" fill="#E8F0FE" stroke="#D2D6DC"/>`;
s+=`<text x="${PAD+10}" y="${top-8}" font-size="14" font-weight="700" fill="#174ea6">Activités</text>`;
s+=`<line x1="${x0}" y1="${top-headH+14}" x2="${x0}" y2="${H-PAD}" stroke="#D2D6DC"/>`;
s+=`</svg>`;

const start=rows[0], end=rows[rows.length-1];
console.log('weeks', weeks, 'size', TW+'x'+H);

const b=await puppeteer.launch({executablePath:'/usr/bin/chromium-browser',headless:'new',args:['--no-sandbox','--disable-dev-shm-usage']});
const p=await b.newPage();
await p.setViewport({width:TW+40,height:H+40,deviceScaleFactor:2});
await p.setContent(`<body style="margin:0">${s}</body>`,{waitUntil:'load'});
const el=await p.$('svg'); await el.screenshot({path:(process.env.OUT||'/tmp/opencode/diag2')+'/3-1_gantt.png'});
await b.close();
console.log('gantt done');
