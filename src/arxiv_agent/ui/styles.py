"""Gradio 页面使用的样式表。

样式单独拆出来的目的是让页面结构和视觉代码分开，阅读时不会被大段 CSS 干扰。
"""

CARD_STYLE = """
<style>
  .app-shell {
    max-width: 1240px;
    margin: 0 auto;
    padding: 28px 16px 56px;
    background: linear-gradient(180deg, #f7f3ea 0%, #efe7d8 100%);
  }
  .hero-block {
    background: linear-gradient(135deg, #fff8ef 0%, #f3dfc6 100%);
    border: 1px solid #e1ceb6;
    border-radius: 24px;
    padding: 24px;
    box-shadow: 0 14px 40px rgba(63, 41, 17, 0.08);
    margin-bottom: 18px;
  }
  .hero-kicker {
    margin: 0 0 8px;
    color: #9c3728;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 12px;
    font-weight: 700;
  }
  .hero-title {
    margin: 0;
    font-size: 38px;
    line-height: 1.0;
    color: #1f1a14;
  }
  .hero-subtitle {
    margin: 12px 0 0;
    font-size: 16px;
    color: #5f574b;
    line-height: 1.65;
  }
  .stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 12px;
    margin: 18px 0;
  }
  .stat-card {
    background: #fffdf9;
    border: 1px solid #e7dac8;
    border-radius: 18px;
    padding: 14px 16px;
    box-shadow: 0 8px 26px rgba(57, 42, 25, 0.05);
  }
  .stat-label {
    display: block;
    color: #6b6256;
    font-size: 12px;
    margin-bottom: 6px;
  }
  .stat-value {
    color: #211c17;
    font-size: 20px;
    font-weight: 700;
  }
  .notice {
    margin-top: 14px;
    padding: 14px 16px;
    border-radius: 18px;
    background: #fffdf8;
    border: 1px solid #eadfce;
    color: #5d5448;
    line-height: 1.65;
  }
  .paper-grid {
    display: grid;
    gap: 18px;
    margin-top: 20px;
  }
  .paper-card {
    background: #fffdf9;
    border: 1px solid #e5d8c7;
    border-radius: 24px;
    padding: 22px;
    box-shadow: 0 10px 30px rgba(58, 42, 21, 0.06);
  }
  .paper-head {
    display: flex;
    justify-content: space-between;
    gap: 16px;
    align-items: flex-start;
  }
  .paper-id {
    margin: 0 0 6px;
    color: #7c715f;
    font-size: 13px;
  }
  .paper-title {
    margin: 0;
    font-size: 24px;
    line-height: 1.25;
    color: #201b15;
  }
  .paper-actions {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
  }
  .paper-link {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    text-decoration: none;
    border-radius: 999px;
    padding: 10px 14px;
    font-size: 14px;
    font-weight: 700;
    background: #9c3728;
    color: #fff8f2;
  }
  .paper-link.secondary {
    background: #efe5d5;
    color: #5b4e3d;
  }
  .paper-meta {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
    margin: 16px 0;
    align-items: center;
  }
  .status-chip {
    display: inline-block;
    padding: 5px 10px;
    border-radius: 999px;
    background: #ede5d7;
    color: #5d5347;
    font-size: 12px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .status-ready { background: rgba(44, 122, 80, 0.13); color: #20663f; }
  .status-missing { background: rgba(183, 115, 0, 0.12); color: #9c6200; }
  .status-failed { background: rgba(180, 35, 24, 0.12); color: #a0261f; }
  .updated-at {
    color: #756b5f;
    font-size: 13px;
  }
  .paper-section {
    margin-top: 18px;
  }
  .paper-section h3 {
    margin: 0 0 8px;
    font-size: 16px;
    color: #312820;
  }
  .paper-section p {
    margin: 0;
    color: #4f463c;
    line-height: 1.75;
    white-space: pre-wrap;
  }
  .error-box {
    margin-top: 18px;
    padding-top: 14px;
    border-top: 1px dashed #decebb;
    color: #a0261f;
  }
  @media (max-width: 768px) {
    .paper-head {
      flex-direction: column;
    }
  }
</style>
"""
