import express from "express";
import OpenAI from "openai";

const app = express();
app.use(express.json());

const client = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY,
});

// route test
app.get("/", (req, res) => {
  res.json({ status: "online", message: "OpenChawn's Fucckkkiinnn' alive" });
});

// 🚀 route GPT
app.post("/chat", async (req, res) => {
  try {
    const { message } = req.body;

    const response = await client.chat.completions.create({
      model: "gpt-4o-mini",
      messages: [{ role: "user", content: message }],
    });

    res.json({
      reply: response.choices[0].message.content,
    });
  } catch (error) {
    console.error(error);
    res.status(500).json({ error: "Erreur GPT" });
  }
});

const PORT = process.env.PORT || 8080;
app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});
