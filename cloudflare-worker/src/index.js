import { Client } from '@neondatabase/serverless';

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    // 1. Pathname Interception
    if (url.pathname === '/api/v1/alpha') {
      
      // 2. Authorization Layer
      const authHeader = request.headers.get('X-Alpha-Token');
      const expectedToken = env.ALPHA_API_KEY;
      
      if (!authHeader || authHeader !== expectedToken) {
        return new Response(
          JSON.stringify({ error: "Unauthorized: Invalid or missing X-Alpha-Token access header" }),
          {
            status: 401,
            headers: {
              'Content-Type': 'application/json',
              'Access-Control-Allow-Origin': '*',
              'Access-Control-Allow-Headers': 'X-Alpha-Token'
            }
          }
        );
      }

      // 3. Database Connection & Query
      const client = new Client(env.DATABASE_URL);
      try {
        await client.connect();
        
        const sql = `
          SELECT timestamp, category, price_index_value, daily_drift_velocity 
          FROM qcomm_catalog_history 
          ORDER BY timestamp DESC 
          LIMIT 100;
        `;
        const result = await client.query(sql);
        
        // 4. Format and Transmit Payload
        return new Response(
          JSON.stringify(result.rows),
          {
            status: 200,
            headers: {
              'Content-Type': 'application/json',
              'Access-Control-Allow-Origin': '*',
              'Access-Control-Allow-Methods': 'GET, OPTIONS',
              'Access-Control-Allow-Headers': 'X-Alpha-Token'
            }
          }
        );
      } catch (err) {
        return new Response(
          JSON.stringify({ error: `Database query failed: ${err.message}` }),
          {
            status: 500,
            headers: {
              'Content-Type': 'application/json',
              'Access-Control-Allow-Origin': '*'
            }
          }
        );
      } finally {
        ctx.waitUntil(client.end());
      }
    }

    // Default response for other paths
    return new Response("aerodata-qcomm API Gateway Active", { status: 200 });
  }
};
