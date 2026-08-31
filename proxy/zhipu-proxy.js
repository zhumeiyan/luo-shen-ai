const https = require('https');

const ZHIPU_HOST = 'open.bigmodel.cn';
const ZHIPU_PATH = '/api/paas/v4/chat/completions';
const ZHIPU_API_KEY = process.env.ZHIPU_API_KEY || '';

module.exports.handler = async (req, res, context) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');
  res.setHeader('Content-Type', 'application/json');

  if (req.method === 'OPTIONS') {
    res.setStatusCode(200);
    res.send('');
    return;
  }

  if (req.method !== 'POST') {
    res.setStatusCode(405);
    res.send(JSON.stringify({ error: 'Method not allowed' }));
    return;
  }

  try {
    const body = req.body || {};
    const { systemPrompt, messageHistory, userMessage, apiKey, overrides } = body;
    const finalApiKey = apiKey || ZHIPU_API_KEY;

    if (!finalApiKey) {
      res.setStatusCode(401);
      res.send(JSON.stringify({ error: 'API Key not configured' }));
      return;
    }

    const messages = [
      { role: 'system', content: systemPrompt },
      ...(messageHistory || []),
      { role: 'user', content: userMessage },
    ];

    const requestBody = JSON.stringify({
      model: 'glm-4',
      messages,
      temperature: overrides?.temperature || 0.9,
      max_tokens: overrides?.max_tokens || 150,
    });

    const zhipuResponse = await fetchZhipu(requestBody, finalApiKey);
    const reply = zhipuResponse.choices?.[0]?.message?.content || '';

    res.setStatusCode(200);
    res.send(JSON.stringify({ reply, raw: zhipuResponse }));
  } catch (err) {
    console.error('Proxy error:', err);
    res.setStatusCode(500);
    res.send(JSON.stringify({ error: err.message }));
  }
};

function fetchZhipu(body, apiKey) {
  return new Promise((resolve, reject) => {
    const options = {
      hostname: ZHIPU_HOST,
      path: ZHIPU_PATH,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${apiKey}`,
        'Content-Length': Buffer.byteLength(body),
      },
    };

    const req = https.request(options, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try { resolve(JSON.parse(data)); }
        catch (e) { reject(new Error('Invalid response from Zhipu')); }
      });
    });

    req.on('error', reject);
    req.write(body);
    req.end();
  });
}
