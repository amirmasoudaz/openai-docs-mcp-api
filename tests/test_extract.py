from __future__ import annotations

from openai_docs_scraper.extract import extract_from_cached_html


HTML_DOC = """
<html>
  <body>
    <header>Global header</header>
    <nav>Left navigation</nav>
    <main>
      <article>
        <h1>Structured Outputs</h1>
        <p>Use structured outputs to return JSON that follows a strict schema.</p>
        <aside>Sidebar content that should be removed.</aside>
        <h2>Example</h2>
        <p>Call the Responses API with a JSON schema.</p>
        <pre><code><span class="line-number">1</span><span>response = client.responses.create()</span></code></pre>
        <footer>Footer content that should be removed.</footer>
      </article>
    </main>
  </body>
</html>
"""


def test_extract_removes_chrome_and_flattens_code_blocks() -> None:
    extracted = extract_from_cached_html(
        url="https://platform.openai.com/docs/guides/structured-outputs",
        title="Structured Outputs",
        raw_html=HTML_DOC,
        raw_body_text=None,
        make_markdown=True,
        keep_main_html=True,
    )

    assert extracted.section == "guides"
    assert "Global header" not in extracted.plain_text
    assert "Left navigation" not in extracted.plain_text
    assert "Sidebar content" not in extracted.plain_text
    assert "Footer content" not in extracted.plain_text
    assert "response = client.responses.create()" in extracted.plain_text
    assert "line-number" not in (extracted.main_html or "")
    assert "Structured Outputs" in (extracted.markdown or "")
    assert "response = client.responses.create()" in (extracted.markdown or "")


def test_extract_prefers_main_like_node() -> None:
    html = """
    <html>
      <body>
        <div class="content">
          <h1>Embeddings</h1>
          <p>Generate vectors for semantic search and retrieval.</p>
        </div>
        <div>tiny</div>
      </body>
    </html>
    """

    extracted = extract_from_cached_html(
        url="https://platform.openai.com/docs/guides/embeddings",
        title="Embeddings",
        raw_html=html,
        raw_body_text=None,
        make_markdown=False,
        keep_main_html=False,
    )

    assert extracted.section == "guides"
    assert extracted.plain_text.startswith("Embeddings")
    assert "semantic search" in extracted.plain_text
