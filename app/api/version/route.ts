export async function GET() {
  return Response.json({ version: process.env.APP_VERSION || "0.3.0" });
}
