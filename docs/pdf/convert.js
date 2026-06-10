const { mdToPdf } = require('C:\\Users\\lucas\\AppData\\Roaming\\npm\\node_modules\\md-to-pdf');
const path = require('path');

const docsDir = path.resolve(__dirname, '..');
const pdfDir = __dirname;
const chromePath = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';

const files = ['ENVIRONNEMENT', 'INSTALLATEUR', 'UTILISATEUR', 'MAINTENANCE', 'MARKETING'];

(async () => {
  for (const file of files) {
    const src = path.join(docsDir, `${file}.md`);
    const dest = path.join(pdfDir, `${file}.pdf`);
    process.stdout.write(`Converting ${file}.md ... `);
    try {
      const pdf = await mdToPdf(
        { path: src },
        {
          dest,
          launch_options: { executablePath: chromePath, args: ['--no-sandbox', '--disable-setuid-sandbox'] },
          pdf_options: { format: 'A4', margin: { top: '20mm', bottom: '20mm', left: '20mm', right: '20mm' } },
        }
      );
      if (pdf) {
        console.log(`OK -> ${file}.pdf`);
      } else {
        console.log('FAILED (no output)');
      }
    } catch (err) {
      console.log(`ERROR: ${err.message}`);
    }
  }
  console.log('Done.');
})();
