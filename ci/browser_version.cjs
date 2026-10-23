const {chromium}=require('../recall-ui/node_modules/@playwright/test');
(async()=>{const browser=await chromium.launch({executablePath:process.argv[2],headless:true});
 try{console.log(browser.version());}finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
